import copy
from fastapi.testclient import TestClient
from test_slice import SliceFixture


class RevisionTests(SliceFixture):
    def test_revert_creates_new_revision_after_preview_and_preserves_pinned_attempt(self):
        course=self.course(); path='/api/courses/'+course['id']; original=course['content']['units'][0]['data']
        session=self.client.post(path+'/sessions',json={'expected_revision':2,'unit_id':'unit-1'}).json()
        replacement=copy.deepcopy(original['questions'][0]);replacement['answer']='B'
        proposal=self.client.post(path+'/proposals',json={'expected_revision':2,'unit_id':'unit-1','target':'question','index':0,'request':'Đổi answer','replacement':replacement}).json()['proposal_id']
        self.client.post('/api/proposals/'+proposal+'/apply',json={'expected_revision':2}).raise_for_status()
        history=self.client.get(path+'/revisions').json()
        self.assertEqual([v['revision'] for v in history],[3,2,1])
        self.assertNotIn('answer',self.client.get(path+'/revisions/2').json()['content']['units'][0]['data']['questions'][0])
        self.assertEqual(self.client.get(path+'/revisions/2?editor=true').json()['content']['units'][0]['data']['questions'][0]['answer'],'A')
        calls=self.provider.calls
        preview=self.client.post(path+'/revert-preview',json={'expected_revision':3,'target_revision':2,'unit_id':'unit-1'}).json()
        self.assertEqual(self.client.get(path).json()['revision'],3)
        viewed=self.client.get('/api/proposals/'+preview['proposal_id']).json()
        self.assertEqual(viewed['after']['units'][0]['data'],original)
        applied=self.client.post('/api/proposals/'+preview['proposal_id']+'/apply',json={'expected_revision':3}).json()
        self.assertEqual(applied['revision'],4)
        self.assertEqual(self.provider.calls,calls)
        self.assertEqual(self.client.get('/api/sessions/'+session['id']).json()['revision'],2)
        self.assertEqual(self.client.get(path+'/editor').json()['content']['units'][0]['data'],original)

    def test_future_preferences_and_sources_do_not_change_generated_lesson_or_original_plan(self):
        course=self.course(); path='/api/courses/'+course['id']
        plan=self.client.get('/api/plans/'+course['plan_id']).json()
        source=self.client.get('/api/sources/'+plan['source_id']+'?revision=2').json()
        original=copy.deepcopy(course['content']['units'][0])
        body={'expected_revision':2,'units':[{'unit_id':'unit-2','title':'Phần tiếp được sửa','objective':'Mục tiêu mới chỉ cho phần tiếp','source_refs':[f['id'] for f in source['fragments']]}],
              'preferences':{'language':'en','goal':'Review only the remaining part','question_types':['mcq','cloze'],'question_count':2,'card_count':1,'unlock_policy':'open'},'request':'Sửa hướng phần chưa tạo'}
        response=self.client.post(path+'/future-plan-preview',json=body);response.raise_for_status();proposal=response.json()['proposal_id']
        self.assertEqual(self.client.get(path).json()['revision'],2)
        self.assertEqual(self.client.get('/api/plans/'+course['plan_id']).json(),plan)
        self.client.post('/api/proposals/'+proposal+'/apply',json={'expected_revision':2}).raise_for_status()
        next_course=self.client.get(path+'/editor').json()
        self.assertNotEqual(next_course['plan_id'],course['plan_id'])
        self.assertEqual(next_course['content']['units'][0]['data'],original['data'])
        self.assertEqual(self.client.get('/api/plans/'+next_course['plan_id']).json()['preferences']['language'],'en')
        self.job(self.client.post(path+'/generate',json={'expected_revision':3,'unit_id':'unit-2'}))
        finished=self.client.get(path+'/editor').json()
        self.assertEqual(finished['content']['units'][0]['data'],original['data'])
        self.assertEqual(len(finished['content']['units'][1]['data']['questions']),2)
        self.assertEqual(finished['content']['units'][1]['generation']['content_language'],'en')
        self.assertEqual(self.client.get('/api/plans/'+course['plan_id']).json(),plan)

    def test_future_preview_rejects_generated_units_foreign_sources_and_stale_apply(self):
        course=self.course();path='/api/courses/'+course['id'];unit=course['content']['units'][1]
        body={'expected_revision':2,'units':[{'unit_id':'unit-1','title':'overwrite','objective':'bad','source_refs':unit['source_refs']}],'request':'Sửa'}
        self.assertEqual(self.client.post(path+'/future-plan-preview',json=body).status_code,409)
        body['units'][0]['unit_id']='unit-2';body['units'][0]['source_refs']=['foreign:1:0']
        self.assertEqual(self.client.post(path+'/future-plan-preview',json=body).status_code,422)
        body['units'][0]['source_refs']=unit['source_refs']
        preview=self.client.post(path+'/future-plan-preview',json=body).json()['proposal_id']
        other=self.client.post(path+'/future-plan-preview',json={**body,'request':'Đề xuất khác'}).json()['proposal_id']
        self.client.post('/api/proposals/'+other+'/apply',json={'expected_revision':2}).raise_for_status()
        self.assertEqual(self.client.post('/api/proposals/'+preview+'/apply',json={'expected_revision':2}).status_code,409)
        self.assertEqual(self.client.get('/api/proposals/'+preview).json()['status'],'preview')

    def test_revision_editor_and_revert_obey_owner_and_active_test(self):
        course=self.course();path='/api/courses/'+course['id']
        foreign=TestClient(self.app,base_url='http://127.0.0.1');foreign.post('/api/session')
        self.assertEqual(foreign.get(path+'/revisions').status_code,404)
        self.assertEqual(foreign.post(path+'/revert-preview',json={'expected_revision':2,'target_revision':1}).status_code,404)
        foreign.close()
        self.client.post(path+'/sessions',json={'expected_revision':2,'unit_id':'unit-1','exercise':'test'}).raise_for_status()
        self.assertEqual(self.client.get(path+'/revisions/2?editor=true').status_code,403)
        self.assertEqual(self.client.post(path+'/revert-preview',json={'expected_revision':2,'target_revision':1}).status_code,403)
