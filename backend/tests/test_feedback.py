from fastapi.testclient import TestClient
from test_slice import SliceFixture
from study_backend.feedback import ShortFeedback


class FeedbackTests(SliceFixture):
    def setUp(self):
        super().setUp()
        self.bad_rubric=False
        generate=self.provider.generate
        async def reply(schema,instruction,fragments):
            if schema is ShortFeedback:
                self.provider.calls+=1;self.provider.instructions.append(instruction)
                return {'criteria':[{'criterion_id':'invented' if self.bad_rubric else 'criterion-0','status':'uncertain','comment':'Thiếu bằng chứng để kết luận.'}],
                        'feedback':'Đối chiếu lại nguồn; đáp án tham khảo có thể cần sửa.','source_refs':[f['id'] for f in fragments],
                        'uncertainties':['Chưa được reviewer xác nhận.'],'reference_may_be_wrong':True}
            return await generate(schema,instruction,fragments)
        self.provider.generate=reply

    def start(self,course,exam=False):
        return self.client.post(f"/api/courses/{course['id']}/sessions",json={'expected_revision':2,'unit_id':'unit-1','exercise':'test' if exam else 'practice'}).json()

    def test_feedback_is_provisional_cached_and_does_not_change_fixed_grading(self):
        course=self.course();session=self.start(course);q=session['questions'][-1]
        path=f"/api/sessions/{session['id']}"
        self.client.post(path+'/answers',json={'item_id':q['id'],'answer':'Câu trả lời của tôi'}).raise_for_status()
        previous=self.client.get(path).json()['answers'][q['id']]
        self.job(self.client.post(path+'/short-feedback',json={'item_id':q['id']}))
        records=self.client.get(path+'/short-feedback').json()
        self.assertEqual(records[0]['status'],'provisional_model_feedback')
        self.assertFalse(records[0]['verified_score'])
        self.assertIsNone(records[0]['estimated_score'])
        self.assertTrue(records[0]['reference_may_be_wrong'])
        self.assertEqual(self.client.get(path).json()['answers'][q['id']],previous)
        calls=self.provider.calls
        cached=self.client.post(path+'/short-feedback',json={'item_id':q['id']}).json()
        self.assertTrue(cached['cached']);self.assertFalse(cached['ai_called'])
        self.assertEqual(self.provider.calls,calls)
        self.assertIn('Câu trả lời của tôi',self.provider.instructions[-1])

    def test_no_feedback_before_answer_or_for_fixed_question(self):
        course=self.course();session=self.start(course);path=f"/api/sessions/{session['id']}/short-feedback";calls=self.provider.calls
        self.assertEqual(self.client.post(path,json={'item_id':session['questions'][-1]['id']}).status_code,409)
        self.assertEqual(self.client.post(path,json={'item_id':session['questions'][0]['id']}).status_code,422)
        self.assertEqual(self.provider.calls,calls)

    def test_wrong_rubric_is_rejected_without_changing_answer(self):
        course=self.course();session=self.start(course);q=session['questions'][-1];path=f"/api/sessions/{session['id']}"
        self.client.post(path+'/answers',json={'item_id':q['id'],'answer':'My answer'}).raise_for_status()
        self.bad_rubric=True
        result=self.client.post(path+'/short-feedback',json={'item_id':q['id']}).json()
        job=self.client.get('/api/jobs/'+result['job_id']).json()
        self.assertEqual(job['status'],'failed')
        self.assertEqual(self.client.get(path+'/short-feedback').json(),[])
        self.assertIsNone(self.client.get(path).json()['answers'][q['id']]['feedback']['correct'])

    def test_feedback_is_private_and_disabled_during_exam(self):
        course=self.course();session=self.start(course,exam=True);q=session['questions'][-1];path=f"/api/sessions/{session['id']}/short-feedback"
        calls=self.provider.calls
        self.assertEqual(self.client.post(path,json={'item_id':q['id']}).status_code,403)
        self.assertEqual(self.provider.calls,calls)
        foreign=TestClient(self.app,base_url='http://127.0.0.1');foreign.post('/api/session')
        self.assertEqual(foreign.get(path).status_code,404)
        self.assertEqual(foreign.post(path,json={'item_id':q['id']}).status_code,404)
        foreign.close()
