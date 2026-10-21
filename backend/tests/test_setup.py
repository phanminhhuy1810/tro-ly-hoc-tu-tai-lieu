from test_slice import SliceFixture
from study_backend.setup import SubjectAnalysis


class SetupTests(SliceFixture):
    def test_ordering_is_not_generated_from_a_bare_list_of_concepts(self):
        source=self.client.post('/api/sources/text',json={'name':'concepts','text':'IPv4 has 32 bits.\nNetwork is one concept.\nBroadcast is another concept.'}).json()
        source=self.client.post(f"/api/sources/{source['id']}/review",json={'expected_revision':1,'texts':[f['text'] for f in source['fragments']]}).json()
        plan_id=self.job(self.client.post('/api/plans',json={**self.preferences(source),'question_types':['cloze','ordering'],'question_count':2}))['plan_id']
        course=self.client.post(f'/api/plans/{plan_id}/approve',json={'expected_revision':1}).json()['course_id']
        calls=self.provider.calls
        result=self.job(self.client.post(f'/api/courses/{course}/generate',json={'expected_revision':1,'unit_id':'unit-1'}))
        self.assertEqual(self.provider.calls-calls,3)  # chapter analysis + reading + cloze, no invented ordering
        unit=self.client.get(f'/api/courses/{course}/editor').json()['content']['units'][0]
        questions=unit['data']['questions']
        self.assertEqual([q['kind'] for q in questions],['cloze'])
        coverage=unit['generation']['question_coverage']
        self.assertFalse(coverage['complete'])
        self.assertEqual((coverage['requested_count'],coverage['generated_count']),(2,1))
        self.assertEqual(coverage['uncreated'][0]['kind'],'ordering')
        self.assertEqual(coverage['uncreated'][0]['origin'],'backend_source_gate')
        self.assertTrue(coverage['uncreated'][0]['reason'])

    def test_model_decline_is_disclosed_separately_from_missing_source_and_complete_coverage(self):
        course=self.course();coverage=course['content']['units'][0]['generation']['question_coverage']
        self.assertTrue(coverage['complete']);self.assertEqual(coverage['uncreated'],[])
        from study_backend.models import QUESTION_DRAFTS
        generate=self.provider.generate
        async def decline(schema,instruction,fragments):
            if schema is QUESTION_DRAFTS['ordering']:
                self.provider.calls+=1
                return {'question':None,'reason':'Test model declined; source content is still available.'}
            return await generate(schema,instruction,fragments)
        self.provider.generate=decline
        # A separate first unit has an explicit procedure; keep the prior
        # completed course/history intact and expose the model's own decline.
        source=self.reviewed()
        plan_id=self.job(self.client.post('/api/plans',json={**self.preferences(source),'question_types':['cloze','ordering'],'question_count':2}))['plan_id']
        other=self.client.post(f'/api/plans/{plan_id}/approve',json={'expected_revision':1}).json()['course_id']
        self.job(self.client.post(f'/api/courses/{other}/generate',json={'expected_revision':1,'unit_id':'unit-1'}))
        partial=self.client.get(f'/api/courses/{other}/editor').json()['content']['units'][0]['generation']['question_coverage']
        self.assertFalse(partial['complete']);self.assertEqual(partial['uncreated'][0]['origin'],'model_declined')
        self.assertIn('source content is still available',partial['uncreated'][0]['reason'])
        prior=self.client.get(f'/api/courses/{course["id"]}/editor').json()
        self.assertEqual(prior['revision'],course['revision'])
    def setUp(self):
        super().setUp()
        generate = self.provider.generate
        async def provider(schema, instruction, fragments):
            if schema is SubjectAnalysis:
                self.provider.calls += 1
                return {'subjects':[{'subject':'Mạng máy tính','evidence':'IPv4 và prefix','source_refs':[fragments[0]['id']]}],
                        'recommended_mode':'cards','reason':'Ghi nhớ định nghĩa','uncertainty':'Đây là gợi ý từ phạm vi nhỏ.'}
            return await generate(schema, instruction, fragments)
        self.provider.generate = provider

    def reviewed(self):
        source = self.source()
        return self.client.post(f"/api/sources/{source['id']}/review", json={'expected_revision':1,'texts':[f['text'] for f in source['fragments']]}).json()

    def test_subject_suggestion_is_editable_private_and_invalidated_by_source_revision(self):
        source = self.source(); path=f"/api/sources/{source['id']}"
        body={'expected_revision':1,'fragment_ids':[f['id'] for f in source['fragments']]}
        self.assertEqual(self.client.post(path+'/analyze',json=body).status_code,409)
        self.assertEqual(self.provider.calls,0)
        source=self.client.post(path+'/review',json={'expected_revision':1,'texts':[f['text'] for f in source['fragments']]}).json()
        body={'expected_revision':2,'fragment_ids':[f['id'] for f in source['fragments']]}
        self.job(self.client.post(path+'/analyze',json=body))
        value=self.client.get(path+'/analysis').json()
        self.assertTrue(value['inference_not_confirmation'])
        self.assertEqual(value['recommended_mode'],'cards')
        choices={'source_id':source['id'],'expected_revision':2,'subject':'Môn tự nhập','goal':'Mục tiêu tự nhập','initial_mode':'learn','language':'source','fragment_ids':body['fragment_ids']}
        clarified=self.client.post('/api/setup/clarify',json=choices).json()
        self.assertTrue(clarified['can_create_preview'])
        self.assertEqual(clarified['preferences']['subject'],'Môn tự nhập')
        self.assertEqual(clarified['preferences']['initial_mode'],'learn')
        self.client.post(path+'/review',json={'expected_revision':2,'texts':[f['text'] for f in source['fragments']]}).raise_for_status()
        self.assertEqual(self.client.get(path+'/analysis').json()['status'],'not_analyzed')

    def test_clarification_only_asks_missing_fields_and_does_not_apply_unknown_defaults(self):
        source=self.reviewed(); calls=self.provider.calls
        body={'source_id':source['id'],'expected_revision':2,'subject':'Mạng máy tính','goal':'unknown','initial_mode':'learn','language':'vi','fragment_ids':[f['id'] for f in source['fragments']]}
        value=self.client.post('/api/setup/clarify',json=body).json()
        self.assertEqual([q['field'] for q in value['questions']],['goal'])
        self.assertFalse(value['defaults_applied'])
        self.assertTrue(value['questions'][0]['requires_confirmation'])
        self.assertEqual(value['questions'][0]['suggested_default'],'Hiểu từ đầu')
        self.assertEqual(self.provider.calls,calls)
        body['goal']='Tự nhập mục tiêu riêng'
        self.assertTrue(self.client.post('/api/setup/clarify',json=body).json()['can_create_preview'])

    def test_selected_types_counts_notes_and_mode_previews_share_one_source_and_course(self):
        source=self.reviewed()
        preferences={**self.preferences(source),'initial_mode':'cards','expected_extraction_revision':2,'question_types':['mcq','cloze'],'question_count':2,'card_count':1,'difficulty':'applied','teacher_notes':'Lưu ý do người học cung cấp','user_notes':'Không đổi văn bản gốc','language':'source','terms_to_keep':['IPv4']}
        plan_id=self.job(self.client.post('/api/plans',json=preferences))['plan_id']
        previews=self.client.get(f'/api/plans/{plan_id}/mode-previews').json()
        self.assertEqual(previews['initial_mode'],'cards')
        self.assertTrue(previews['shared_course'])
        self.assertEqual(previews['practice']['groups'][0]['planned_questions'],2)
        approved=self.client.post(f'/api/plans/{plan_id}/approve',json={'expected_revision':1}).json()
        course_id=approved['course_id']
        self.job(self.client.post(f'/api/courses/{course_id}/generate',json={'expected_revision':1,'unit_id':'unit-1'}))
        course=self.client.get(f'/api/courses/{course_id}/editor').json()
        data=course['content']['units'][0]['data']
        self.assertEqual([q['kind'] for q in data['questions']],['mcq','cloze'])
        self.assertEqual(len(data['cards']),1)
        self.assertEqual(data['questions'][0]['difficulty_basis'],'creator_request_not_measured')
        result=self.client.post(f'/api/courses/{course_id}/sessions',json={'expected_revision':2,'unit_id':'unit-1','difficulty':'applied','question_count':2})
        self.assertEqual(result.status_code,200)
        self.assertEqual(self.client.get(f"/api/sources/{source['id']}").json()['fragments'],source['fragments'])

    def test_excluded_or_foreign_source_and_impossible_distribution_are_rejected(self):
        source=self.reviewed(); preferences=self.preferences(source)
        self.assertEqual(self.client.post('/api/plans',json={**preferences,'excluded_fragment_ids':[preferences['fragment_ids'][0]]}).status_code,422)
        self.assertEqual(self.client.post('/api/plans',json={**preferences,'excluded_fragment_ids':['foreign:1:0']}).status_code,422)
        self.assertEqual(self.client.post('/api/plans',json={**preferences,'expected_extraction_revision':1}).status_code,409)
        self.assertEqual(self.client.post('/api/plans',json={**preferences,'question_types':['mcq','cloze'],'question_count':1}).status_code,422)
        self.assertEqual(self.client.post('/api/plans',json={**preferences,'goal':'unknown'}).status_code,409)
        self.assertEqual(self.provider.calls,0)

    def test_repeated_questions_do_not_fill_requested_count_with_duplicates(self):
        source=self.reviewed()
        plan_id=self.job(self.client.post('/api/plans',json={**self.preferences(source),'question_types':['mcq'],'question_count':2}))['plan_id']
        course=self.client.post(f'/api/plans/{plan_id}/approve',json={'expected_revision':1}).json()['course_id']
        response=self.client.post(f'/api/courses/{course}/generate',json={'expected_revision':1,'unit_id':'unit-1'})
        job=self.client.get('/api/jobs/'+response.json()['job_id']).json()
        self.assertEqual(job['status'],'succeeded')
        self.assertTrue(job['partial']['reading'])
        self.assertEqual(sum(bool(value['question']) for value in job['partial']['questions'].values()),1)
        self.assertEqual(job['partial']['question_rejections']['mcq:2']['code'],'QUESTION_DUPLICATE')
        current=self.client.get(f'/api/courses/{course}/editor').json()
        self.assertEqual(current['revision'],2)
        coverage=current['content']['units'][0]['generation']['question_coverage']
        self.assertEqual((coverage['requested_count'],coverage['generated_count'],coverage['complete']),(2,1,False))
