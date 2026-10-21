"""Original principles can support a later exercise without escaping its chapter."""
import copy
import json
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from study_backend import chapter_evidence
from study_backend.gemini import ProviderError
from study_backend.models import QUESTION_DRAFTS, LessonReading
from test_slice import SliceFixture


def example():
    texts=['Network giữ nguyên NetID và đưa HostID về 0; broadcast đặt HostID lên 1.',
           'Số host dùng được là 2^h - 2, với h là số bit HostID.',
           'Prefix và subnet mask phân định số bit mạng và số bit host.',
           'Subnet mask có các bit1 liên tiếp rồi đến các bit0.',
           'Classless cho phép chọn ranh giới NetID và HostID bằng prefix.',
           'Biểu diễn một IPv4 bằng32bits và bốn octet.',
           'Bài tập: Cho172.100.112.4/19, tính network, broadcast và số host.']
    fragments=[{'id':f'chapter:2:{i}','text':text,'locator':{'type':'page','page':i+1}} for i,text in enumerate(texts)]
    unit={'id':'exercise','title':'Vận dụng prefix','objective':'Tính network, broadcast và host dùng được từ IP và prefix.','source_refs':[fragments[-1]['id']]}
    prefs={'goal':unit['objective']}
    brief={'summary':'Network, broadcast và số host suy ra từ ranh giới prefix.',
           'key_ideas':['HostID về0 cho network; lên1 cho broadcast.','2^h - 2 host dùng được.'],
           'connections':['Prefix xác định số bit HostID.'],'question_targets':[]}
    return fragments,unit,prefs,brief


class EvidenceSelectionTests(unittest.TestCase):
    def test_selects_actual_principles_earlier_in_chapter_keeps_focus_and_does_not_mutate_it(self):
        fragments,unit,prefs,brief=example();before=copy.deepcopy(unit)
        selected,scope=chapter_evidence.select(fragments,unit,prefs,brief,'context')
        self.assertEqual(unit,before);self.assertEqual(scope['focus_source_refs'],unit['source_refs'])
        self.assertIn('chapter:2:0',scope['support_source_refs']);self.assertIn('chapter:2:1',scope['support_source_refs'])
        self.assertTrue(set(scope['input_source_refs'])<=set(f['id'] for f in fragments))
        self.assertLessEqual(len(scope['support_source_refs']),4)
        self.assertEqual(scope['ai_calls'],0);self.assertTrue(scope['relevance_is_not_entailment'])
        self.assertEqual([f['id'] for f in selected],scope['input_source_refs'])

    def test_budget_never_drops_or_truncates_focus_to_fit_support(self):
        fragments,unit,prefs,brief=example()
        fragments[-1]['text']='network prefix host broadcast '*290
        fragments[0]['text']='network host broadcast principle '*80
        selected,scope=chapter_evidence.select(fragments,unit,prefs,brief,'context')
        self.assertIn(fragments[-1],selected)
        self.assertEqual(next(f['text'] for f in selected if f['id']==fragments[-1]['id']),fragments[-1]['text'])
        self.assertTrue(scope['omitted']);self.assertTrue(all(x['reason']=='input_budget' for x in scope['omitted']))

    def test_resume_keeps_exact_evidence_when_the_new_ranking_would_change(self):
        fragments,unit,prefs,brief=example()
        selected,scope=chapter_evidence.select(fragments,unit,prefs,brief,'context')
        with patch('study_backend.chapter_evidence.MAX_SUPPORT_FRAGMENTS',0):
            again,pinned=chapter_evidence.select(fragments,unit,prefs,{},'context',scope)
        self.assertEqual(again,selected);self.assertEqual(pinned,scope)
        damaged=copy.deepcopy(scope);damaged['input_source_refs'].append('unapproved')
        damaged['sha256']=chapter_evidence.digest({k:v for k,v in damaged.items() if k!='sha256'})
        with self.assertRaises(HTTPException):chapter_evidence.validate(damaged,fragments,unit,'context')
        with self.assertRaises(HTTPException):chapter_evidence.validate(scope,fragments,unit,'other-context')
        changed=copy.deepcopy(fragments);changed[0]['text']+=' changed'
        with self.assertRaises(HTTPException):chapter_evidence.validate(scope,changed,unit,'context')

    def test_existing_evidence_is_preserved_and_not_expanded_beyond_four_supports(self):
        fragments,unit,prefs,brief=example()
        first,scope=chapter_evidence.select(fragments,unit,prefs,brief,'context')
        unit['source_refs']=scope['input_source_refs'];unit['generation']={'evidence_scope':scope}
        second,after=chapter_evidence.select(fragments,unit,prefs,{},'context')
        self.assertTrue(set(scope['input_source_refs'])<=set(after['input_source_refs']))
        self.assertEqual(after['focus_source_refs'],scope['focus_source_refs']);self.assertLessEqual(len(after['support_source_refs']),4)


class EvidenceFlowTests(SliceFixture):
    def draft(self):
        fragments,_,_,_=example()
        raw='\n'.join(f['text'] for f in fragments)+'\nPRIVATE_EXCLUDED notes about passwords.'
        source=self.client.post('/api/sources/text',json={'name':'chapter.txt','text':raw}).json()
        source=self.client.post('/api/sources/'+source['id']+'/review',json={'expected_revision':1,'texts':[f['text'] for f in source['fragments']]}).json()
        refs=[f['id'] for f in source['fragments'][:-1]]
        prefs={**self.preferences(source),'fragment_ids':refs,'excluded_fragment_ids':[source['fragments'][-1]['id']],
               'unlock_policy':'open','question_types':['mcq','cloze'],'question_count':2}
        plan=self.client.post('/api/plans/from-source-sections',json=prefs).json()
        outline={'title':'Network chapter','units':[{'title':'Nguyên lý','objective':'Hiểu nguyên lý IP','source_refs':refs[:-1]},
                  {'title':'Bài tập vận dụng','objective':'Tính network, broadcast và host từ IP và prefix.','source_refs':refs[-1:]}]}
        edit=self.client.put('/api/plans/'+plan['id'],json={'expected_version':1,'outline':outline});edit.raise_for_status()
        cid=self.client.post('/api/plans/'+plan['id']+'/approve',json={'expected_revision':2}).json()['course_id']
        return self.client.get('/api/courses/'+cid+'/editor').json(),source

    def generate(self,course,**extra):
        return self.client.post('/api/courses/'+course['id']+'/generate',json={'expected_revision':course['revision'],'unit_id':'unit-2',**extra})

    def test_failed_reading_pins_evidence_before_first_output_and_reuses_whole_chapter_on_explicit_retry(self):
        course,_=self.draft();original=self.provider.generate;calls=[]
        async def invalid_reading(schema,instruction,fragments):
            calls.append(schema)
            if schema is LessonReading:raise ValueError('Missing mindmap source_refs from model')
            return await original(schema,instruction,fragments)
        self.provider.generate=invalid_reading
        response=self.generate(course);response.raise_for_status();jid=response.json()['job_id']
        failed=self.client.get('/api/jobs/'+jid).json()
        self.assertEqual(failed['status'],'failed');self.assertIsNone(failed['partial']['reading'])
        scope=failed['partial']['evidence_scope'];self.assertTrue(scope['support_source_refs'])
        self.assertTrue(failed['partial']['chapter_context']['complete'])
        self.assertFalse(any(schema in QUESTION_DRAFTS.values() for schema in calls))
        self.assertEqual(self.client.get('/api/courses/'+course['id']+'/editor').json(),course)
        self.provider.generate=original
        with patch('study_backend.chapter_evidence.MAX_SUPPORT_FRAGMENTS',0):
            self.job(self.generate(course,resume_job_id=jid))
        unit=self.client.get('/api/courses/'+course['id']+'/editor').json()['content']['units'][1]
        self.assertEqual(unit['generation']['evidence_scope'],scope)
        self.assertEqual(self.client.get('/api/jobs/'+jid).json()['partial'],failed['partial'])

    def test_support_citations_survive_save_source_lookup_and_inline_help_without_private_excluded_text(self):
        course,source=self.draft();original=self.provider.generate;received=[]
        async def model(schema,instruction,fragments):
            received.append((schema,copy.deepcopy(fragments)))
            if schema is QUESTION_DRAFTS['mcq']:
                exercise=next(f for f in fragments if f['text'].startswith('Bài tập:'))
                principle=next(f for f in fragments if 'giữ nguyên' in f['text'])
                return {'question':{'kind':'mcq','prompt':'Với172.100.112.4/19, địa chỉ network là gì?',
                        'options':['172.100.96.0','172.100.112.0'],'answer':'172.100.96.0',
                        'explanation':'Áp dụng ranh giới prefix và đưa các bit HostID về0.',
                        'source_refs':[exercise['id'],principle['id']]},'reason':''}
            return await original(schema,instruction,fragments)
        self.provider.generate=model
        self.job(self.generate(course))
        current=self.client.get('/api/courses/'+course['id']+'/editor').json();unit=current['content']['units'][1]
        scope=unit['generation']['evidence_scope'];question=unit['data']['questions'][0]
        self.assertEqual(scope['focus_source_refs'],course['content']['units'][1]['source_refs'])
        self.assertTrue(set(question['source_refs'])&set(scope['support_source_refs']))
        shown=self.client.get('/api/courses/'+course['id']+'/source-fragments?unit_id=unit-2').json()
        self.assertTrue(set(question['source_refs'])<=set(f['id'] for f in shown))
        self.assertIn('giữ nguyên',' '.join(f['text'] for f in shown if f['id'] in question['source_refs']))
        self.assertNotIn('PRIVATE_EXCLUDED',json.dumps(received,default=str,ensure_ascii=False))
        session=self.client.post('/api/courses/'+course['id']+'/sessions',json={'expected_revision':2,'unit_id':'unit-2'}).json()
        # This route pins the exact question sources, including its theory.
        response=self.client.post('/api/sessions/'+session['id']+'/items/'+session['questions'][0]['id']+'/help',json={})
        response.raise_for_status()
        thread=self.client.get('/api/help/threads/'+response.json()['thread_id']).json()
        self.assertEqual(set(question['source_refs']),{f['id'] for f in thread['source_excerpts']})
        self.assertIn('giữ nguyên',' '.join(f['text'] for f in thread['source_excerpts']))

    def test_resume_keeps_support_for_saved_reading_and_question_without_reselection(self):
        course,_=self.draft();original=self.provider.generate;seen=[]
        async def broken(schema,instruction,fragments):
            seen.append((schema,[f['id'] for f in fragments]))
            if schema is QUESTION_DRAFTS['cloze']:raise ProviderError('CONNECTION_FAILED','Test disconnect',True)
            return await original(schema,instruction,fragments)
        self.provider.generate=broken
        response=self.generate(course);jid=response.json()['job_id'];failed=self.client.get('/api/jobs/'+jid).json()
        self.assertEqual(failed['status'],'failed');scope=failed['partial']['evidence_scope']
        self.assertTrue(scope['support_source_refs'])
        self.provider.generate=original
        with patch('study_backend.chapter_evidence.MAX_SUPPORT_FRAGMENTS',0):self.job(self.generate(course,resume_job_id=jid))
        unit=self.client.get('/api/courses/'+course['id']+'/editor').json()['content']['units'][1]
        self.assertEqual(unit['generation']['evidence_scope'],scope)
        self.assertEqual(unit['data']['sections'],failed['partial']['reading']['sections'])
        self.assertEqual(self.client.get('/api/jobs/'+jid).json()['partial'],failed['partial'])

    def test_completion_support_is_previewed_and_does_not_change_old_attempts(self):
        course,_=self.draft();original=self.provider.generate
        async def decline(schema,*args):
            if schema is QUESTION_DRAFTS['cloze']:return {'question':None,'reason':'Fixture decline'}
            return await original(schema,*args)
        self.provider.generate=decline
        with patch('study_backend.chapter_evidence.MAX_SUPPORT_FRAGMENTS',0):self.job(self.generate(course))
        self.provider.generate=original
        cid=course['id'];before=self.client.get('/api/courses/'+cid+'/editor').json();unit=before['content']['units'][1]
        old_session=self.client.post('/api/courses/'+cid+'/sessions',json={'expected_revision':2,'unit_id':'unit-2'}).json()
        completed=self.job(self.client.post('/api/courses/'+cid+'/question-completion',json={'expected_revision':2,'unit_id':'unit-2','stages':['cloze']}))
        preview=self.client.get('/api/proposals/'+completed['proposal_id']).json()
        self.assertEqual(preview['before']['source_refs'],unit['source_refs'])
        self.assertTrue(set(unit['source_refs'])<set(preview['after']['source_refs']))
        self.assertEqual(self.client.get('/api/courses/'+cid+'/editor').json(),before)
        applied=self.client.post('/api/proposals/'+completed['proposal_id']+'/apply',json={'expected_revision':2});applied.raise_for_status()
        after=self.client.get('/api/courses/'+cid+'/editor').json()['content']['units'][1]
        self.assertEqual(after['data']['questions'][:-1],unit['data']['questions'])
        self.assertEqual(self.client.get('/api/sessions/'+old_session['id']).json()['questions'],old_session['questions'])
        self.assertTrue(set(after['data']['questions'][0]['source_refs'])<=set(after['source_refs']))
