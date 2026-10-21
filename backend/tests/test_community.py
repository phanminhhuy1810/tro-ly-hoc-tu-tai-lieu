from fastapi.testclient import TestClient
from test_slice import SliceFixture, FIXTURE_SOURCE


class CommunityTests(SliceFixture):
    def peer(self):
        client=TestClient(self.app,base_url='http://127.0.0.1');client.post('/api/session').raise_for_status();self.addCleanup(client.close);return client

    def publish(self,course,visibility='public',original=False):
        path=f"/api/courses/{course['id']}"
        preview=self.client.post(path+'/publication-preview',json={'expected_revision':course['revision'],'visibility':visibility,'share_original':original})
        preview.raise_for_status();value=preview.json()
        applied=self.client.post('/api/publications/'+value['publication_id']+'/apply',json={'expected_revision':course['revision']});applied.raise_for_status()
        self.assertEqual(applied.json()['coin_for_publishing'],0)
        return value

    def complete(self,client,course_id,revision,wrong=False):
        response=client.post(f'/api/courses/{course_id}/sessions',json={'expected_revision':revision,'unit_id':'unit-1'});response.raise_for_status();session=response.json()
        for q in session['questions']:
            if q['kind']=='mcq':answer='option-1' if wrong else 'option-0'
            elif q['kind']=='cloze':answer='0' if wrong else '62'
            elif q['kind']=='matching':answer={'left-0':'option-1' if wrong else 'option-0','left-1':'option-0' if wrong else 'option-1'}
            elif q['kind']=='ordering':answer=['option-1','option-0'] if wrong else ['option-0','option-1']
            else:answer='My response'
            client.post(f"/api/sessions/{session['id']}/answers",json={'item_id':q['id'],'answer':answer}).raise_for_status()
        result=client.post(f"/api/sessions/{session['id']}/complete");result.raise_for_status()
        return session,result.json()

    def test_publication_requires_preview_and_enrollment_does_not_grant_original_or_editor(self):
        course=self.course();path=f"/api/courses/{course['id']}";peer=self.peer()
        self.assertEqual(peer.get(path).status_code,404)
        preview=self.client.post(path+'/publication-preview',json={'expected_revision':2,'visibility':'public'}).json()
        self.assertEqual(peer.get('/api/community').json(),[])
        self.client.post('/api/publications/'+preview['publication_id']+'/apply',json={'expected_revision':2}).raise_for_status()
        overview=peer.get('/api/community').json()[0]
        self.assertNotIn('preferences',overview);self.assertNotIn('source_id',overview)
        self.assertEqual(peer.get(path).status_code,404)
        peer.post(path+'/enroll').raise_for_status()
        value=peer.get(path).json()
        self.assertEqual(value['access_role'],'learner');self.assertIsNone(value['plan_id'])
        self.assertNotIn('preferences',value['content'])
        self.assertNotIn('generation',value['content']['units'][0])
        self.assertNotIn('answer',value['content']['units'][0]['data']['questions'][0])
        source=self.client.get('/api/plans/'+course['plan_id']).json()['source_id']
        self.assertEqual(peer.get('/api/sources/'+source+'/original').status_code,404)
        self.assertEqual(peer.get('/api/sources/'+source).status_code,404)
        self.assertEqual(peer.get(path+'/editor').status_code,404)
        self.assertEqual(peer.post(path+'/generate',json={'expected_revision':2,'unit_id':'unit-2'}).status_code,404)
        fragments=peer.get(path+'/source-fragments').json();self.assertTrue(fragments)
        self.assertEqual({f['id'] for f in fragments},set(course['content']['units'][0]['source_refs']))

    def test_each_learner_has_own_progress_history_notebook_cards_and_chat(self):
        course=self.course();path=f"/api/courses/{course['id']}";first=self.peer();second=self.peer();self.publish(course)
        first.post(path+'/enroll');second.post(path+'/enroll')
        session,result=self.complete(first,course['id'],2,wrong=True);self.assertEqual(result['score'],0)
        self.assertTrue(first.get(path).json()['content']['units'][1]['unlocked'])
        self.assertFalse(second.get(path).json()['content']['units'][1]['unlocked'])
        self.assertFalse(self.client.get(path).json()['content']['units'][1]['unlocked'])
        self.assertEqual(second.get(path+'/history').json(),[])
        self.assertEqual(second.get('/api/sessions/'+session['id']).status_code,404)
        q=session['questions'][0]
        card=first.post('/api/cards/from-question',json={'session_id':session['id'],'item_id':q['id']});card.raise_for_status()
        self.assertFalse(any(c['kind']=='personal' for c in second.get('/api/cards?course_id='+course['id']).json()))
        note=first.post('/api/notebook',json={'body':'private learner note','course_id':course['id'],'source_refs':q['source_refs']});note.raise_for_status()
        self.assertEqual(second.get('/api/notebook').json(),[])
        help_job=first.post(path+'/chat',json={'unit_id':'unit-1','message':'help learner'});help_job.raise_for_status()
        self.assertEqual(second.get(path+'/chat').json(),[])
        self.assertEqual(self.client.get(path+'/chat').json(),[])
        self.assertTrue(first.get(path+'/chat').json())

    def test_locked_generated_material_hidden_from_new_learner_and_old_attempt_pinned_after_creator_fix(self):
        course=self.course();path=f"/api/courses/{course['id']}"
        self.complete(self.client,course['id'],2)
        self.job(self.client.post(path+'/generate',json={'expected_revision':2,'unit_id':'unit-2'}))
        course=self.client.get(path+'/editor').json();self.publish(course);peer=self.peer();peer.post(path+'/enroll')
        view=peer.get(path).json();self.assertFalse(view['content']['units'][1]['unlocked']);self.assertIsNone(view['content']['units'][1]['data'])
        self.assertEqual(peer.post(path+'/sessions',json={'expected_revision':3,'unit_id':'unit-2'}).status_code,403)
        session=peer.post(path+'/sessions',json={'expected_revision':3,'unit_id':'unit-1'}).json()
        q=course['content']['units'][0]['data']['questions'][0].copy();q['answer']='B'
        proposal=self.client.post(path+'/proposals',json={'expected_revision':3,'unit_id':'unit-1','target':'question','index':0,'request':'fix','replacement':q}).json()['proposal_id']
        self.client.post('/api/proposals/'+proposal+'/apply',json={'expected_revision':3}).raise_for_status()
        grade=peer.post(f"/api/sessions/{session['id']}/answers",json={'item_id':session['questions'][0]['id'],'answer':'option-0'}).json()
        self.assertTrue(grade['correct']);self.assertEqual(peer.get('/api/sessions/'+session['id']).json()['revision'],3)

    def test_original_sharing_and_invite_revocation_are_separate_from_kept_private_history(self):
        course=self.course();path=f"/api/courses/{course['id']}";peer=self.peer();self.publish(course,'shared',True)
        invite=self.client.post(path+'/invite').json()['code'];peer.post('/api/community/join',json={'code':invite}).raise_for_status()
        source=self.client.get('/api/plans/'+course['plan_id']).json()['source_id']
        self.assertEqual(peer.get('/api/sources/'+source+'/original').content,FIXTURE_SOURCE)
        session,_=self.complete(peer,course['id'],2)
        peer.post('/api/notebook',json={'body':'kept note'}).raise_for_status()
        self.publish(course,'private',False)
        self.assertEqual(peer.get(path).status_code,404)
        self.assertEqual(peer.get('/api/sources/'+source+'/original').status_code,404)
        self.assertEqual(peer.post('/api/community/join',json={'code':invite}).status_code,404)
        self.assertEqual(peer.get('/api/sessions/'+session['id']).status_code,200)
        self.assertEqual(peer.get('/api/notebook').json()[0]['body'],'kept note')

    def test_positive_feedback_event_only_once_no_self_or_publish_reward_and_report_does_not_edit_bank(self):
        course=self.course();path=f"/api/courses/{course['id']}";self.publish(course);peer=self.peer();peer.post(path+'/enroll')
        route=f"/api/community/{course['id']}/feedback"
        self.assertEqual(self.client.put(route,json={'liked':True,'rating':5}).status_code,409)
        value=peer.put(route,json={'liked':True,'rating':5}).json();self.assertTrue(value['new_quality_event_id']);self.assertEqual(value['coin_awarded'],0)
        peer.put(route,json={'liked':False})
        self.assertIsNone(peer.put(route,json={'liked':True,'rating':4}).json()['new_quality_event_id'])
        with self.app.state.database.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM community_quality_events').fetchone()[0],1)
        before=self.client.get(path+'/editor').json()
        report=peer.post(f"/api/community/{course['id']}/reports",json={'reason':'question unclear','unit_id':'unit-1'}).json()
        self.assertFalse(report['bank_changed'])
        self.assertEqual(self.client.get(path+'/editor').json(),before)
        self.assertEqual(len(self.client.get(path+'/reports').json()),1)
        self.assertEqual(peer.get(path+'/reports').status_code,404)

    def test_real_reward_policy_caps_peers_and_relike_cannot_remint_tomorrow(self):
        from datetime import datetime, timedelta, timezone
        course = self.course();path = '/api/courses/' + course['id']
        economy = self.app.state.economy;economy.enabled = True
        clock = datetime(2026, 10, 15, 18, tzinfo=timezone.utc);economy.clock = lambda: clock
        self.publish(course)
        self.assertEqual(self.client.get('/api/wallet').json()['balance'], 20)
        peers = [self.peer() for _ in range(3)]
        route = f"/api/community/{course['id']}/feedback"
        for peer, expected in zip(peers, [2, 2, 0]):
            peer.post(path + '/enroll').raise_for_status()
            feedback = peer.put(route, json={'liked': True, 'rating': 5});feedback.raise_for_status()
            self.assertEqual(feedback.json()['coin_awarded'], expected)
        self.assertEqual(self.client.get('/api/wallet').json()['balance'], 24)
        clock += timedelta(days=1)
        peers[2].put(route, json={'liked': False})
        self.assertEqual(peers[2].put(route, json={'liked': True}).json()['coin_awarded'], 0)
        self.assertEqual(self.client.get('/api/wallet').json()['balance'], 24)
        self.assertEqual(peers[0].post(f"/api/community/{course['id']}/reports", json={'reason': 'bad binding', 'unit_id': 'unit-1', 'question_id': 'unknown'}).status_code, 422)
