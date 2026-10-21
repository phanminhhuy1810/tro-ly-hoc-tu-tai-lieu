"""Per-question source failures must not destroy usable lesson stages."""
import json
from fastapi.testclient import TestClient
from test_slice import SliceFixture
from study_backend.models import QUESTION_DRAFTS, LessonReading
from study_backend.generation_contract import validated_generation
from study_backend.gemini import ProviderError


class QuestionStageRecoveryTests(SliceFixture):
    def prepared(self, kinds=None):
        source=self.source()
        source=self.client.post(f"/api/sources/{source['id']}/review",json={'expected_revision':1,'texts':[f['text'] for f in source['fragments']]}).json()
        prefs=self.preferences(source)
        if kinds:prefs['question_types']=kinds
        plan=self.job(self.client.post('/api/plans',json=prefs))['plan_id']
        course=self.client.post(f'/api/plans/{plan}/approve',json={'expected_revision':1}).json()['course_id']
        return course,source

    def reject_cloze(self):
        original=self.provider.generate
        async def generate(schema,instruction,fragments):
            if schema is QUESTION_DRAFTS['cloze']:
                self.provider.calls+=1
                value={'question':{'kind':'cloze','prompt':None,'answer':'invented answer',
                      'explanation':'Unverified fixture.','source_refs':[fragments[0]['id']]}}
                return validated_generation(schema,json.dumps(value),fragments=fragments).model_dump()
            return await original(schema,instruction,fragments)
        self.provider.generate=generate

    def test_bad_mcq_key_does_not_stop_other_types_or_get_repaired(self):
        course,_=self.prepared();original=self.provider.generate;calls=self.provider.calls
        async def generate(schema,instruction,fragments):
            if schema is QUESTION_DRAFTS['mcq']:
                self.provider.calls+=1
                draft={'question':{'kind':'mcq','prompt':'Pick a network','options':['A network','B broadcast','C host'],
                    'answer':'A','explanation':'Unmatched letter is not a valid key.','source_refs':[fragments[0]['id']]},'reason':None}
                return validated_generation(schema,json.dumps(draft),fragments=fragments).model_dump()
            return await original(schema,instruction,fragments)
        self.provider.generate=generate
        r=self.client.post(f'/api/courses/{course}/generate',json={'expected_revision':1,'unit_id':'unit-1'})
        self.job(r);job=self.client.get('/api/jobs/'+r.json()['job_id']).json()
        self.assertEqual(self.provider.calls-calls,7)
        self.assertEqual(job['partial']['question_rejections']['mcq']['code'],'MCQ_KEY_OR_CHOICES_INVALID')
        unit=self.client.get(f'/api/courses/{course}/editor').json()['content']['units'][0]
        self.assertEqual([q['kind'] for q in unit['data']['questions']],['cloze','matching','ordering','short_answer'])
        self.assertEqual(unit['generation']['question_coverage']['generated_count'],4)
        self.assertFalse(unit['generation']['question_coverage']['complete'])

    def test_duplicate_prompt_is_excluded_but_not_retried_or_published(self):
        course,_=self.prepared();original=self.provider.generate;first=[];calls=self.provider.calls
        async def generate(schema,instruction,fragments):
            value=await original(schema,instruction,fragments)
            if schema is QUESTION_DRAFTS['mcq']:first.append(value['question']['prompt'])
            if schema is QUESTION_DRAFTS['short_answer']:value['question']['prompt']=first[0]
            return value
        self.provider.generate=generate
        r=self.client.post(f'/api/courses/{course}/generate',json={'expected_revision':1,'unit_id':'unit-1'})
        self.job(r);job=self.client.get('/api/jobs/'+r.json()['job_id']).json()
        self.assertEqual(self.provider.calls-calls,7)
        self.assertEqual(job['partial']['question_rejections']['short_answer']['code'],'QUESTION_DUPLICATE')
        unit=self.client.get(f'/api/courses/{course}/editor').json()['content']['units'][0]
        self.assertEqual([q['kind'] for q in unit['data']['questions']],['mcq','cloze','matching','ordering'])
        self.assertFalse(unit['generation']['question_coverage']['complete'])

    def test_only_invalid_mcq_does_not_publish_an_empty_lesson(self):
        course,_=self.prepared(['mcq']);original=self.provider.generate
        async def generate(schema,instruction,fragments):
            if schema is QUESTION_DRAFTS['mcq']:
                draft={'question':{'kind':'mcq','prompt':'Pick one','options':['one','two'],'answer':'A',
                    'explanation':'No valid key','source_refs':[fragments[0]['id']]}}
                return validated_generation(schema,json.dumps(draft),fragments=fragments).model_dump()
            return await original(schema,instruction,fragments)
        self.provider.generate=generate
        r=self.client.post(f'/api/courses/{course}/generate',json={'expected_revision':1,'unit_id':'unit-1'})
        job=self.client.get('/api/jobs/'+r.json()['job_id']).json()
        self.assertEqual(job['status'],'failed');self.assertTrue(job['partial']['reading'])
        self.assertIsNone(job['partial']['questions']['mcq']['question'])
        self.assertEqual(self.client.get(f'/api/courses/{course}').json()['revision'],1)

    def test_rejected_cloze_continues_once_records_reason_and_remaining_questions_are_practicable(self):
        course,source=self.prepared();self.reject_cloze();calls=self.provider.calls
        response=self.client.post(f'/api/courses/{course}/generate',json={'expected_revision':1,'unit_id':'unit-1'})
        self.job(response);jid=response.json()['job_id'];job=self.client.get(f'/api/jobs/{jid}').json()
        self.assertEqual(self.provider.calls-calls,7)  # chapter analysis + reading + each requested kind once
        unit=self.client.get(f'/api/courses/{course}/editor').json()['content']['units'][0]
        self.assertEqual([q['kind'] for q in unit['data']['questions']],['mcq','matching','ordering','short_answer'])
        c=unit['generation']['question_coverage']
        self.assertEqual((c['generated_count'],c['requested_count'],c['complete']),(4,5,False))
        self.assertEqual(c['uncreated'][0]['origin'],'backend_question_validation')
        self.assertEqual(c['uncreated'][0]['code'],'CLOZE_SOURCE_UNVERIFIED')
        self.assertEqual(job['partial']['question_rejections']['cloze']['code'],'CLOZE_SOURCE_UNVERIFIED')
        rejected=[r for r in job['progress']['requests'] if r['schema']=='ClozeDraft'][0]
        self.assertEqual(rejected['phase'],'rejected');self.assertIsNotNone(rejected['elapsed_ms'])
        session=self.client.post(f'/api/courses/{course}/sessions',json={'expected_revision':2,'unit_id':'unit-1'}).json()
        self.assertEqual(len(session['questions']),4)
        graded=self.client.post(f"/api/sessions/{session['id']}/answers",json={'item_id':session['questions'][0]['id'],'answer':'A'}).json()
        self.assertTrue(graded['correct'])
        self.assertEqual(self.client.get(f"/api/sources/{source['id']}").json()['revision'],2)
        outsider=TestClient(self.app,base_url='http://127.0.0.1');outsider.post('/api/session')
        self.assertEqual(outsider.get(f'/api/jobs/{jid}').status_code,404);outsider.close()

    def test_no_usable_questions_does_not_commit_empty_lesson_but_keeps_reading_and_reason(self):
        course,_=self.prepared(['cloze']);self.reject_cloze()
        r=self.client.post(f'/api/courses/{course}/generate',json={'expected_revision':1,'unit_id':'unit-1'})
        job=self.client.get('/api/jobs/'+r.json()['job_id']).json()
        self.assertEqual(job['status'],'failed');self.assertTrue(job['partial']['reading'])
        self.assertIsNone(job['partial']['questions']['cloze']['question'])
        self.assertEqual(self.client.get(f'/api/courses/{course}').json()['revision'],1)

    def test_connection_failure_still_stops_and_explicit_resume_reuses_reading_and_mcq(self):
        course,_=self.prepared();original=self.provider.generate;calls=[]
        async def offline(schema,*args):
            calls.append(schema)
            if schema is QUESTION_DRAFTS['cloze']:raise ProviderError('CONNECTION_FAILED','Fixture disconnected',True)
            return await original(schema,*args)
        self.provider.generate=offline
        r=self.client.post(f'/api/courses/{course}/generate',json={'expected_revision':1,'unit_id':'unit-1'})
        jid=r.json()['job_id'];job=self.client.get('/api/jobs/'+jid).json()
        self.assertEqual(job['status'],'failed');self.assertEqual(job['error']['code'],'CONNECTION_FAILED')
        self.assertEqual(list(job['partial']['questions']),['mcq'])
        self.provider.generate=original;self.reject_cloze();before=self.provider.calls
        result=self.client.post(f'/api/courses/{course}/generate',json={'expected_revision':1,'unit_id':'unit-1','resume_job_id':jid})
        self.job(result);after=self.client.get('/api/jobs/'+result.json()['job_id']).json()
        self.assertEqual(self.provider.calls-before,4)
        self.assertEqual(after['partial']['reading'],job['partial']['reading'])
        self.assertEqual(after['partial']['questions']['mcq'],job['partial']['questions']['mcq'])
        self.assertEqual(self.client.get('/api/jobs/'+jid).json(),job)
        self.assertEqual(after['progress']['reused_stages'],3)  # chapter + reading + MCQ reused

    def test_unproved_ordering_isolated_without_repeating_generation_or_losing_other_types(self):
        course,_=self.prepared();original=self.provider.generate;calls=self.provider.calls
        async def generate(schema,instruction,fragments):
            if schema is QUESTION_DRAFTS['ordering']:
                self.provider.calls+=1
                draft={'question':{'kind':'ordering','prompt':'Arrange unproved paraphrases',
                    'options':['First invented action','Second invented action'],
                    'explanation':'Unverified test candidate.','source_refs':[fragments[0]['id']]}}
                return validated_generation(schema,json.dumps(draft),fragments=fragments).model_dump()
            return await original(schema,instruction,fragments)
        self.provider.generate=generate
        r=self.client.post(f'/api/courses/{course}/generate',json={'expected_revision':1,'unit_id':'unit-1'})
        self.job(r);job=self.client.get('/api/jobs/'+r.json()['job_id']).json()
        self.assertEqual(self.provider.calls-calls,7)
        self.assertEqual(job['status'],'succeeded')
        rejection=job['partial']['question_rejections']['ordering']
        self.assertEqual(rejection['code'],'ORDERING_SOURCE_UNPROVEN')
        unit=self.client.get(f'/api/courses/{course}/editor').json()['content']['units'][0]
        self.assertEqual([q['kind'] for q in unit['data']['questions']],['mcq','cloze','matching','short_answer'])
        self.assertFalse(unit['generation']['question_coverage']['complete'])
        self.assertEqual(unit['generation']['question_coverage']['uncreated'][0]['origin'],'backend_question_validation')

    def test_foreign_ordering_ref_still_fails_instead_of_becoming_a_soft_rejection(self):
        course,_=self.prepared();original=self.provider.generate
        async def generate(schema,instruction,fragments):
            if schema is QUESTION_DRAFTS['ordering']:
                draft={'question':{'kind':'ordering','prompt':'Arrange source steps',
                    'options':['Read the prefix','Calculate host bits'],
                    'explanation':'From an unauthorized reference.','source_refs':['foreign:1:0']}}
                return validated_generation(schema,json.dumps(draft),fragments=fragments).model_dump()
            return await original(schema,instruction,fragments)
        self.provider.generate=generate
        r=self.client.post(f'/api/courses/{course}/generate',json={'expected_revision':1,'unit_id':'unit-1'})
        job=self.client.get('/api/jobs/'+r.json()['job_id']).json()
        self.assertEqual(job['status'],'failed');self.assertEqual(job['error']['code'],'SOURCE_REFERENCE_MISMATCH')
        self.assertNotIn('ordering',job['partial'].get('question_rejections',{}))
        self.assertEqual(self.client.get(f'/api/courses/{course}').json()['revision'],1)
