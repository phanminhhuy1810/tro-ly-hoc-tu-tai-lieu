"""Chapter-aware scoped correction, private checkpoints and manual independence.

All inference in these tests uses explicit adapters, not factual-quality scores.
"""
import asyncio
import copy
import json
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from study_backend.app import create_app
from study_backend.chapter_context import ChapterBrief
from study_backend.gemini import ProviderError
from study_backend.models import Card, Lesson, QUESTION_DRAFTS
from study_backend.providers import Choice
from study_backend.correction_prompt import INPUT_STRATEGY, LEGACY_STRATEGY
from test_slice import SliceFixture, TestProvider


class CorrectionContextTests(SliceFixture):
    def body(self, course, **extra):
        return {'expected_revision': course['revision'], 'unit_id': 'unit-1', 'target': 'question', 'index': 0,
                'request': 'Sửa giải thích đúng nguyên lý; giữ dạng và phần không cần sửa.', **extra}

    def post(self, course, **extra):
        return self.client.post(f"/api/courses/{course['id']}/proposals", json=self.body(course, **extra))

    def editor(self, course):
        return self.client.get(f"/api/courses/{course['id']}/editor").json()

    def clear_context(self):
        # A ready lesson from a pre-chapter release: don't trust its metadata
        # as proof that an actual chapter checkpoint still exists.
        with self.app.state.database.connection(write=True) as db: db.execute('DELETE FROM chapter_contexts')

    def legacy_chapter(self, long=False):
        text = ['IPv4 has32bits; prefix determines host bits. ' + ('Giải thích nguyên lý. ' * (48 if long else 1))
                for _ in range(18 if long else 3)]
        text[-1] += ' TAIL_PRINCIPLE: network/broadcast delimit the usable host range.'
        source = self.client.post('/api/sources/text', json={'name':'chapter.txt', 'text':'\n'.join(text+['EXCLUDED_PRIVATE_PART'])}).json()
        source = self.client.post(f"/api/sources/{source['id']}/review", json={'expected_revision':1,
            'texts':[f['text'] for f in source['fragments']]}).json()
        refs = [f['id'] for f in source['fragments'][:-1]]
        prefs = {**self.preferences(source), 'fragment_ids':refs, 'excluded_fragment_ids':[source['fragments'][-1]['id']],
                 'question_types':['mcq'], 'question_count':1, 'unlock_policy':'open'}
        plan = self.client.post('/api/plans/from-source-sections', json=prefs).json()
        units = [{'title':'First section','objective':'Explain the prefix and boundaries.','source_refs':refs[:1]}]
        units += [{'title':f'Remaining section {i}', 'objective':'Connect the chapter principles.', 'source_refs':refs[i:i+5]}
                  for i in range(1,len(refs),5)]
        self.client.put('/api/plans/'+plan['id'], json={'expected_version':1, 'outline':{'title':'Approved chapter',
            'units':units}}).raise_for_status()
        cid = self.client.post('/api/plans/'+plan['id']+'/approve', json={'expected_revision':2}).json()['course_id']
        # Populate the existing lesson as an older valid release would. No
        # model chapter call occurs; the correction must perform that reading.
        data = asyncio.run(self.provider.generate(Lesson, '', [source['fragments'][0]]))
        data['questions'] = data['questions'][:1]
        with self.app.state.database.connection(write=True) as db:
            row = db.execute('SELECT content_json FROM course_revisions WHERE course_id=? AND revision=1',(cid,)).fetchone()
            content = json.loads(row[0]); content['units'][0]['data'] = data
            db.execute('UPDATE course_revisions SET content_json=? WHERE course_id=? AND revision=1',(json.dumps(content),cid))
        return self.client.get(f'/api/courses/{cid}/editor').json(), source, refs

    def record(self):
        original = self.provider.generate; events = []
        async def generate(schema, instruction, fragments):
            events.append({'schema':schema, 'instruction':instruction, 'fragments':copy.deepcopy(fragments)})
            if schema is Card:
                self.provider.calls += 1
                return {'front':'Network?', 'back':'Corrected test card', 'source_refs':[fragments[0]['id']]}
            return await original(schema, instruction, fragments)
        self.provider.generate = generate
        return events

    def manual_question_fixture(self, course, index, replacement):
        result=self.post(course,index=index,replacement=replacement).json()
        self.client.post('/api/proposals/'+result['proposal_id']+'/apply',json={'expected_revision':course['revision']}).raise_for_status()
        return self.editor(course)

    def test_ai_question_reconsiders_visible_choices_can_change_key_and_keeps_creator_metadata(self):
        course=self.course();q=copy.deepcopy(course['content']['units'][0]['data']['questions'][0])
        q.update(explanation='OLD_SOLUTION_NOT_EVIDENCE',rubric=['OLD_RUBRIC_NOT_EVIDENCE'],difficulty='hard',difficulty_basis='creator_request_not_measured')
        course=self.manual_question_fixture(course,0,q);original=self.provider.generate;seen=[]
        async def rederive(schema,instruction,fragments):
            self.assertIs(schema,QUESTION_DRAFTS['mcq']);seen.append(instruction)
            self.assertNotIn('OLD_SOLUTION_NOT_EVIDENCE',instruction);self.assertNotIn('OLD_RUBRIC_NOT_EVIDENCE',instruction)
            self.assertIn(q['prompt'],instruction)
            for option in q['options']:self.assertIn(option,instruction)
            value=await original(schema,instruction,fragments);value['question']['answer']='B'
            return value
        self.provider.generate=rederive;result=self.job(self.post(course,request='Kiểm tra lại key từ nguồn, giữ nguyên lựa chọn.'))
        preview=self.client.get('/api/proposals/'+result['proposal_id']).json()
        self.assertEqual(preview['before'],q);self.assertEqual(preview['after']['answer'],'B')
        self.assertEqual(preview['after']['difficulty'],'hard');self.assertEqual(preview['after']['difficulty_basis'],'creator_request_not_measured')
        self.assertEqual(self.editor(course),course);self.assertEqual(len(seen),1)
        self.client.post('/api/proposals/'+result['proposal_id']+'/apply',json={'expected_revision':course['revision']}).raise_for_status()
        history=self.editor(course)['content']['units'][0]['generation']['correction_history'][-1]
        self.assertEqual(history['input_strategy'],INPUT_STRATEGY)

    def test_short_answer_old_reference_explanation_and_rubric_are_not_model_facts(self):
        course=self.course();index=4;q=copy.deepcopy(course['content']['units'][0]['data']['questions'][index])
        q.update(answer='OLD_REFERENCE_KEY_MARKER',explanation='OLD_EXPLANATION_MARKER',rubric=['OLD_RUBRIC_MARKER'])
        course=self.manual_question_fixture(course,index,q);events=self.record();result=self.job(self.post(course,index=index,request='Xét lại dữ kiện từ nguồn và nêu điều kiện còn thiếu.'))
        self.assertEqual([x['schema'] for x in events],[QUESTION_DRAFTS['short_answer']])
        for marker in (q['answer'],q['explanation'],q['rubric'][0]):self.assertNotIn(marker,events[0]['instruction'])
        self.assertIn(q['prompt'],events[0]['instruction']);self.assertIn('BỐI CẢNH TOÀN CHƯƠNG',events[0]['instruction'])
        preview=self.client.get('/api/proposals/'+result['proposal_id']).json()
        self.assertEqual(preview['before'],q);self.assertEqual(self.editor(course),course)

    def test_legacy_correction_reads_all_approved_chapter_before_one_typed_question_and_only_previews(self):
        course, source, refs = self.legacy_chapter(); events = self.record()
        before = copy.deepcopy(course); result = self.job(self.post(course))
        self.assertEqual(self.editor(course), before)
        reads = [e for e in events if e['schema'] is ChapterBrief]
        self.assertEqual({f['id'] for e in reads for f in e['fragments']}, set(refs))
        self.assertIn('TAIL_PRINCIPLE', json.dumps([f['text'] for e in reads for f in e['fragments']]))
        self.assertNotIn('EXCLUDED_PRIVATE_PART', json.dumps(events, default=str))
        self.assertIs(events[-1]['schema'], QUESTION_DRAFTS['mcq'])
        self.assertIn('BỐI CẢNH TOÀN CHƯƠNG', events[-1]['instruction'])
        self.assertEqual([f['id'] for f in events[-1]['fragments']], course['content']['units'][0]['source_refs'])
        proposal = self.client.get('/api/proposals/'+result['proposal_id']).json()
        self.assertEqual(proposal['scope'], {'unit_id':'unit-1','target':'question','index':0})
        self.assertEqual(proposal['after']['kind'], 'mcq')

    def test_cache_reused_scoped_apply_preserves_other_content_old_provider_and_attempt(self):
        course = self.course(); before = copy.deepcopy(course['content'])
        session = self.client.post(f"/api/courses/{course['id']}/sessions", json={'expected_revision':2,'unit_id':'unit-1'}).json()
        old_session = self.client.get('/api/sessions/'+session['id']).json()
        events = self.record(); result = self.job(self.post(course))
        self.assertEqual([e['schema'] for e in events], [QUESTION_DRAFTS['mcq']])
        self.client.post('/api/proposals/'+result['proposal_id']+'/apply', json={'expected_revision':2}).raise_for_status()
        after = self.editor(course); a, b = after['content']['units'][0], before['units'][0]
        self.assertEqual(after['revision'],3)
        self.assertEqual(after['content']['units'][1:],before['units'][1:])
        self.assertEqual(a['data']['questions'][1:],b['data']['questions'][1:])
        for key in ('title','sections','cards','mindmap'): self.assertEqual(a['data'][key], b['data'][key])
        for key,value in b['generation'].items(): self.assertEqual(a['generation'][key],value)
        history = a['generation']['correction_history'][-1]
        self.assertTrue(history['chapter_context']['complete'])
        self.assertEqual(history['scope']['source_plan_id'],course['plan_id'])
        self.assertEqual(self.client.get('/api/sessions/'+session['id']).json(),old_session)

    def test_long_chapter_continues_without_proposal_or_coin_charge_and_rejects_completed_resume(self):
        course,_,_ = self.legacy_chapter(long=True); events = self.record(); self.app.state.economy.enabled = True
        before = self.client.get('/api/wallet').json(); latest = None; intermediates = []
        with patch('study_backend.chapter_context.MAX_READ_CALLS_PER_JOB',1):
            for turn in range(12):
                body = self.body(course, **({'resume_job_id':latest} if latest else {})); path=f"/api/courses/{course['id']}/proposals"
                quote = self.client.post(path,json=body).json()['detail']
                response = self.client.post(path,json=body,headers={'Coin-Quote-Id':quote['quote_id'],'Idempotency-Key':f'correction-part-{turn}'})
                response.raise_for_status(); latest=response.json()['job_id']
                job = self.client.get('/api/jobs/'+latest).json(); self.assertEqual(job['status'],'succeeded',job)
                if job['result'].get('proposal_id'): break
                intermediates.append(job)
                self.assertTrue(job['result']['continuation_required'])
                self.assertEqual(self.editor(course),course)
                self.assertEqual(self.client.get('/api/wallet').json(),before)
                with self.app.state.database.connection() as db:self.assertEqual(db.execute('SELECT count(*) FROM revision_proposals').fetchone()[0],0)
            else:self.fail('Finite chapter did not finish')
        self.assertGreater(len(intermediates),0)
        question_events = [e for e in events if e['schema'] in QUESTION_DRAFTS.values()]
        self.assertEqual(len(question_events),1)
        self.assertEqual(self.post(course,resume_job_id=latest).status_code,409)
        self.assertEqual(self.client.get('/api/wallet').json()['balance'],before['balance']-self.app.state.economy.policy['prices']['correction'])
        self.assertEqual(self.client.get('/api/wallet').json()['held'],0)

    def test_failed_request_restart_resumes_context_without_repeating_reading(self):
        course = self.course(); original = self.provider.generate
        async def fail(schema,*args):
            if schema is QUESTION_DRAFTS['mcq']: raise ProviderError('CONNECTION_FAILED','Fixture disconnected',True)
            return await original(schema,*args)
        self.provider.generate=fail
        jid=self.post(course).json()['job_id'];old=self.client.get('/api/jobs/'+jid).json();self.assertEqual(old['status'],'failed')
        self.assertTrue(old['partial']['chapter_context']['complete'])
        self.client.close();self.app=create_app(self.app.state.database.path,Path(self.temp.name)/'sources',self.provider,economy_enabled=False)
        self.client=TestClient(self.app,base_url='http://127.0.0.1',cookies=self.client.cookies)
        self.provider.generate=original;events=self.record()
        self.job(self.post(course,resume_job_id=jid))
        self.assertEqual([e['schema'] for e in events],[QUESTION_DRAFTS['mcq']])
        self.assertEqual(self.client.get('/api/jobs/'+jid).json(),old)
        self.assertEqual(self.editor(course),course)

    def test_saved_valid_replacement_reused_after_transaction_failure_without_new_model_or_relabel(self):
        course=self.course();original_finish=self.app.state.jobs.finish
        def fail(db,jid,result):
            if result.get('proposal_id'):raise ProviderError('CONNECTION_FAILED','After checkpoint failure',True)
            return original_finish(db,jid,result)
        with patch.object(self.app.state.jobs,'finish',fail):
            jid=self.post(course).json()['job_id']
        old=self.client.get('/api/jobs/'+jid).json();self.assertEqual(old['status'],'failed')
        self.assertIsNotNone(old['partial']['replacement'])
        other=TestProvider();router=self.app.state.jobs.provider_router;router.choices['other']=Choice('other','Other',other)
        self.client.put('/api/ai/selection',json={'model_id':'other','expected_revision':0}).raise_for_status()
        calls=self.provider.calls;result=self.job(self.post(course,resume_job_id=jid))
        self.assertEqual(self.provider.calls,calls);self.assertEqual(other.calls,0)
        self.client.post('/api/proposals/'+result['proposal_id']+'/apply',json={'expected_revision':2}).raise_for_status()
        history=self.editor(course)['content']['units'][0]['generation']['correction_history'][-1]
        self.assertEqual(history['provider'],old['partial']['replacement_provider'])
        self.assertEqual(history['input_strategy'],old['partial']['replacement_input_strategy'])
        self.assertEqual(self.client.get('/api/jobs/'+jid).json(),old)

    def test_legacy_valid_replacement_without_strategy_is_not_relabelled_as_new_inputs(self):
        course=self.course();finish=self.app.state.jobs.finish
        def fail(db,jid,result):
            if result.get('proposal_id'):raise ProviderError('CONNECTION_FAILED','After checkpoint',True)
            return finish(db,jid,result)
        with patch.object(self.app.state.jobs,'finish',fail):jid=self.post(course).json()['job_id']
        with self.app.state.database.connection(write=True) as db:
            partial=json.loads(db.execute('SELECT partial_json FROM jobs WHERE id=?',(jid,)).fetchone()[0])
            partial.pop('replacement_input_strategy')
            db.execute('UPDATE jobs SET partial_json=? WHERE id=?',(json.dumps(partial),jid))
        old=self.client.get('/api/jobs/'+jid).json();calls=self.provider.calls
        result=self.job(self.post(course,resume_job_id=jid));self.assertEqual(self.provider.calls,calls)
        self.client.post('/api/proposals/'+result['proposal_id']+'/apply',json={'expected_revision':course['revision']}).raise_for_status()
        history=self.editor(course)['content']['units'][0]['generation']['correction_history'][-1]
        self.assertEqual(history['input_strategy'],LEGACY_STRATEGY);self.assertEqual(history['provider'],old['partial']['replacement_provider'])
        self.assertEqual(self.client.get('/api/jobs/'+jid).json(),old)

    def test_scope_tamper_foreign_owner_and_changed_request_do_not_start_a_job_or_hold_coin(self):
        course=self.course();original=self.provider.generate
        async def fail(schema,*args):
            if schema is QUESTION_DRAFTS['mcq']:raise ProviderError('CONNECTION_FAILED','Stop',True)
            return await original(schema,*args)
        self.provider.generate=fail;jid=self.post(course).json()['job_id'];calls=self.provider.calls
        wallet=self.client.get('/api/wallet').json()
        with self.app.state.database.connection() as db:count=db.execute('SELECT count(*) FROM jobs').fetchone()[0]
        for extra in ({'request':'Other request'},{'index':1},{'target':'card'},{'expected_revision':1}):
            self.assertEqual(self.post(course,resume_job_id=jid,**extra).status_code,409)
        peer=TestClient(self.app,base_url='http://127.0.0.1');peer.post('/api/session')
        self.assertEqual(peer.post(f"/api/courses/{course['id']}/proposals",json=self.body(course,resume_job_id=jid)).status_code,404);peer.close()
        with self.app.state.database.connection(write=True) as db:
            partial=json.loads(db.execute('SELECT partial_json FROM jobs WHERE id=?',(jid,)).fetchone()[0]);partial['correction_scope']['input_sha256']='changed'
            db.execute('UPDATE jobs SET partial_json=? WHERE id=?',(json.dumps(partial),jid))
        self.assertEqual(self.post(course,resume_job_id=jid).status_code,409)
        self.assertEqual(self.provider.calls,calls);self.assertEqual(self.client.get('/api/wallet').json(),wallet)
        with self.app.state.database.connection() as db:self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],count)

    def test_manual_is_available_with_zero_coin_and_removed_model_and_does_not_read_chapter(self):
        course=self.course();self.clear_context();self.app.state.economy.enabled=True
        self.client.get('/api/wallet')
        with self.app.state.database.connection(write=True) as db:db.execute('UPDATE wallets SET balance=0')
        self.app.state.jobs.provider_router.choices.clear()
        replacement=copy.deepcopy(course['content']['units'][0]['data']['questions'][0]);replacement['explanation']='User correction'
        calls=self.provider.calls;result=self.post(course,replacement=replacement);result.raise_for_status()
        self.client.post('/api/proposals/'+result.json()['proposal_id']+'/apply',json={'expected_revision':2}).raise_for_status()
        self.assertEqual(self.provider.calls,calls)
        with self.app.state.database.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM chapter_contexts').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM jobs WHERE task=\'correction\'').fetchone()[0],0)
        self.assertEqual(self.client.get('/api/wallet').json()['held'],0)
        self.assertEqual(self.post(course,replacement=replacement,resume_job_id='old').status_code,422)

    def test_decline_and_unbound_source_do_not_publish_or_auto_retry_and_refund(self):
        for mode in ('decline','foreign'):
            with self.subTest(mode=mode):
                self.app.state.economy.enabled=False
                course=self.course();original=self.provider.generate;calls=self.provider.calls
                self.app.state.economy.enabled=True;wallet=self.client.get('/api/wallet').json()
                async def bad(schema,instruction,fragments):
                    if schema is QUESTION_DRAFTS['mcq']:
                        self.provider.calls+=1
                        if mode=='decline':return {'question':None,'reason':'Missing source for requested correction.'}
                        value=await original(schema,instruction,fragments);value['question']['source_refs']=['foreign'];return value
                    return await original(schema,instruction,fragments)
                self.provider.generate=bad
                path=f"/api/courses/{course['id']}/proposals";body=self.body(course)
                quote=self.client.post(path,json=body).json()['detail']
                response=self.client.post(path,json=body,headers={'Coin-Quote-Id':quote['quote_id'],'Idempotency-Key':'reject-'+mode})
                response.raise_for_status()
                jid=response.json()['job_id'];job=self.client.get('/api/jobs/'+jid).json()
                self.assertEqual(job['status'],'failed');self.assertIsNone(job['result'])
                self.assertEqual(self.editor(course),course)
                self.assertEqual(self.provider.calls-calls,1 if mode=='decline' else 2)
                if mode=='decline':self.assertEqual(job['error']['code'],'CORRECTION_SOURCE_INSUFFICIENT')
                else:self.assertEqual(job['error']['code'],'SOURCE_REFERENCE_MISMATCH')
                self.assertEqual(self.client.get('/api/wallet').json(),wallet)
                self.provider.generate=original

    def test_cancel_during_question_keeps_chapter_and_explicit_resume_charges_only_once(self):
        course=self.course();original=self.provider.generate;self.app.state.economy.enabled=True
        wallet=self.client.get('/api/wallet').json();path=f"/api/courses/{course['id']}/proposals"
        quote=self.client.post(path,json=self.body(course)).json()['detail']
        async def scenario():
            entered=asyncio.Event()
            async def block(schema,*args):
                if schema is QUESTION_DRAFTS['mcq']:
                    entered.set();await asyncio.Event().wait()
                return await original(schema,*args)
            self.provider.generate=block
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://127.0.0.1',cookies=self.client.cookies) as client:
                task=asyncio.create_task(client.post(path,json=self.body(course),headers={'Coin-Quote-Id':quote['quote_id'],'Idempotency-Key':'cancel-this-correction'}))
                await asyncio.wait_for(entered.wait(),3)
                with self.app.state.database.connection() as db:
                    jid=db.execute("SELECT id FROM jobs WHERE task='correction' AND status='running'").fetchone()[0]
                (await client.post('/api/jobs/'+jid+'/cancel')).raise_for_status()
                await asyncio.wait_for(task,3)
                job=(await client.get('/api/jobs/'+jid)).json()
                self.assertEqual(job['status'],'cancelled');self.assertTrue(job['partial']['chapter_context']['complete'])
                self.assertIsNone(job['partial']['replacement'])
                return jid
        jid=asyncio.run(scenario());self.assertEqual(self.editor(course),course)
        self.assertEqual(self.client.get('/api/wallet').json(),wallet)
        self.provider.generate=original;events=self.record();body=self.body(course,resume_job_id=jid)
        quote=self.client.post(path,json=body).json()['detail']
        self.job(self.client.post(path,json=body,headers={'Coin-Quote-Id':quote['quote_id'],'Idempotency-Key':'resume-cancelled-correction'}))
        self.assertEqual([e['schema'] for e in events],[QUESTION_DRAFTS['mcq']])
        self.assertEqual(self.client.get('/api/wallet').json()['balance'],wallet['balance']-self.app.state.economy.policy['prices']['correction'])
        self.assertEqual(self.client.get('/api/wallet').json()['held'],0)

    def test_idempotent_replay_with_absent_or_null_resume_never_generates_or_charges_twice(self):
        course=self.course();self.app.state.economy.enabled=True;calls=self.provider.calls
        path=f"/api/courses/{course['id']}/proposals";body=self.body(course);wallet=self.client.get('/api/wallet').json()
        quote=self.client.post(path,json=body).json()['detail']
        headers={'Idempotency-Key':'one-correction-intent','Coin-Quote-Id':quote['quote_id']}
        response=self.client.post(path,json=body,headers=headers);self.job(response)
        replay=self.client.post(path,json={**body,'resume_job_id':None},headers={'Idempotency-Key':headers['Idempotency-Key']})
        self.assertEqual(replay.json(),response.json());self.assertEqual(self.provider.calls-calls,1)
        self.assertEqual(self.client.post(path,json={**body,'request':'A changed intent'},headers=headers).status_code,409)
        self.assertEqual(self.client.get('/api/wallet').json()['balance'],wallet['balance']-self.app.state.economy.policy['prices']['correction'])
        with self.app.state.database.connection() as db:self.assertEqual(db.execute('SELECT count(*) FROM revision_proposals').fetchone()[0],1)

    def test_correction_reads_units_own_approved_plan_not_course_default_or_newer_extraction(self):
        course=self.course();path=f"/api/courses/{course['id']}"
        old_plan=self.client.get('/api/plans/'+course['plan_id']).json()
        old_source=self.client.get('/api/sources/'+old_plan['source_id']).json()
        source=self.client.post('/api/sources/text',json={'name':'other-chapter.txt','text':'NEW_UNIT_CONTEXT IPv4 has 32 bits.\nProcedure: (1) read the prefix; (2) calculate host bits.'}).json()
        source=self.client.post('/api/sources/'+source['id']+'/review',json={'expected_revision':1,'texts':[f['text'] for f in source['fragments']]}).json()
        refs=[f['id'] for f in source['fragments']]
        proposal=self.client.post(path+'/future-plan-preview',json={'expected_revision':2,'request':'Use new source in unit 2',
            'preferences':{'unlock_policy':'open'},'units':[{'unit_id':'unit-2','title':'New source','objective':'Explain prefix boundaries.',
            'source_id':source['id'],'expected_extraction_revision':source['revision'],'source_refs':refs}]}).json()
        self.client.post('/api/proposals/'+proposal['proposal_id']+'/apply',json={'expected_revision':2}).raise_for_status()
        course=self.editor(course);self.clear_context()
        self.client.post('/api/sources/'+old_source['id']+'/review',json={'expected_revision':old_source['revision'],
            'texts':[f['text']+' LATEST_UNAPPROVED_FOR_OLD_UNIT' for f in old_source['fragments']]}).raise_for_status()
        events=self.record();result=self.job(self.post(course))
        reads=[e for e in events if e['schema'] is ChapterBrief]
        self.assertEqual({f['id'] for e in reads for f in e['fragments']},set(old_plan['preferences']['fragment_ids']))
        self.assertNotIn('NEW_UNIT_CONTEXT',json.dumps(events,default=str));self.assertNotIn('LATEST_UNAPPROVED_FOR_OLD_UNIT',json.dumps(events,default=str))
        self.client.post('/api/proposals/'+result['proposal_id']+'/apply',json={'expected_revision':course['revision']}).raise_for_status()
        history=self.editor(course)['content']['units'][0]['generation']['correction_history'][-1]
        self.assertNotEqual(history['scope']['source_plan_id'],course['plan_id'])
        self.assertEqual(history['scope']['source_plan_id'],old_plan['id'])
        self.assertEqual(history['scope']['source_id'],old_source['id']);self.assertEqual(history['scope']['extraction_revision'],old_source['revision'])

    def test_ai_card_and_lesson_use_same_chapter_cache_without_relabelling_initial_generation(self):
        course=self.course();events=self.record()
        for target in ('card','lesson'):
            result=self.job(self.post(course,target=target))
            preview=self.client.get('/api/proposals/'+result['proposal_id']).json()
            self.assertEqual(preview['scope']['target'],target)
            self.assertEqual(self.editor(course),course)
        self.assertEqual([e['schema'] for e in events],[Card,Lesson])

    def test_exam_defers_replacement_request_and_error_in_http_and_sse_without_destroying_checkpoint(self):
        course=self.course();marker='PRIVATE_CORRECTION_ANSWER_MARKER';finish=self.app.state.jobs.finish
        def fail(db,jid,result):
            if result.get('proposal_id'):raise ProviderError('CONNECTION_FAILED',marker,True)
            return finish(db,jid,result)
        with patch.object(self.app.state.jobs,'finish',fail):jid=self.post(course,request=marker).json()['job_id']
        old=self.client.get('/api/jobs/'+jid).json();self.assertEqual(old['context']['request'],marker)
        self.assertIsNotNone(old['partial']['replacement'])
        exam=self.client.post(f"/api/courses/{course['id']}/sessions",json={'expected_revision':2,'unit_id':'unit-1','exercise':'test'}).json()
        current=self.client.get('/api/jobs/'+jid).json();self.assertTrue(current['feedback_deferred'])
        self.assertNotIn(marker,json.dumps(current));self.assertNotIn('replacement',current['partial'])
        self.assertNotIn(marker,self.client.get('/api/jobs/'+jid+'/events?once=true').text)
        self.client.post('/api/sessions/'+exam['id']+'/cancel').raise_for_status()
        self.assertEqual(self.client.get('/api/jobs/'+jid).json(),old)
