import asyncio
import copy
from datetime import datetime, timedelta, timezone
import json
import time
import uuid

import httpx
from fastapi.testclient import TestClient

from study_backend.app import create_app
from study_backend.models import ChatReply
from test_slice import SliceFixture


class Clock:
    def __init__(self): self.value = datetime(2026, 10, 17, tzinfo=timezone.utc)
    def __call__(self): return self.value
    def add(self, seconds): self.value += timedelta(seconds=seconds)


class RoomTests(SliceFixture):
    def setUp(self):
        super().setUp()
        self.clock = Clock(); self.app.state.rooms.clock = self.clock
        self.course_value = self.course()
        self.peers = []

    def tearDown(self):
        for peer in self.peers: peer.close()
        super().tearDown()

    def peer(self):
        peer = TestClient(self.app, base_url='http://127.0.0.1'); peer.post('/api/session').raise_for_status()
        self.peers.append(peer); return peer

    def create(self, count=4, key=None):
        body = {'course_id': self.course_value['id'], 'expected_revision': 2, 'unit_ids': ['unit-1'],
                'question_count': count, 'seconds_per_question': 5, 'nickname': 'Host'}
        response = self.client.post('/api/rooms', json=body, headers={'Idempotency-Key': key or str(uuid.uuid4())})
        response.raise_for_status(); room = response.json()
        self.room = room; self.base = '/api/rooms/' + room['room_id']
        return room, body

    def join(self, peer, nickname='Learner'):
        result = peer.post('/api/rooms/join', json={'code': self.room['join_code'], 'nickname': nickname})
        result.raise_for_status(); return result.json()

    def snapshot(self, client=None):
        result = (client or self.client).get(self.base); result.raise_for_status(); return result.json()

    def action(self, name, client=None, version=None, key=None):
        client = client or self.client
        version = self.snapshot(client)['event_index'] if version is None else version
        return client.post(self.base + '/' + name, json={'expected_event_index': version}, headers={'Idempotency-Key': key or str(uuid.uuid4())})

    def answer(self, value, client=None, snapshot=None, key=None):
        client = client or self.client; snapshot = snapshot or self.snapshot(client)
        return client.post(self.base + '/answers', json={'event_index': snapshot['question_event_index'],
            'question_id': snapshot['question']['id'], 'answer': value}, headers={'Idempotency-Key': key or str(uuid.uuid4())})

    def finish(self, peer, values=None):
        values = values or ['option-0', '62', {'left-0': 'option-0', 'left-1': 'option-1'}, ['option-0', 'option-1']]
        self.action('start').raise_for_status()
        for value in values:
            self.answer(value).raise_for_status(); self.answer(value, peer).raise_for_status()
            self.assertEqual(self.snapshot()['phase'], 'question_closed')
            self.action('next').raise_for_status()
        self.assertEqual(self.snapshot()['phase'], 'finished')

    def test_create_pins_only_valid_fixed_questions_and_requires_private_owner_access(self):
        calls = self.provider.calls
        room, body = self.create(key='create-once')
        self.assertEqual(room['question_count'], 4)
        self.assertTrue(any('Tự luận' in x['reason'] for x in room['omitted']))
        self.assertEqual(self.provider.calls, calls)
        replay = self.client.post('/api/rooms', json=body, headers={'Idempotency-Key': 'create-once'}).json()
        self.assertEqual(replay['room_id'], room['room_id']); self.assertNotIn('join_code', replay)
        self.assertEqual(self.client.post('/api/rooms', json={**body, 'question_count': 1}, headers={'Idempotency-Key': 'create-once'}).status_code, 409)
        peer = self.peer()
        self.assertEqual(peer.post('/api/rooms', json=body, headers={'Idempotency-Key': 'foreign'}).status_code, 404)
        self.assertEqual(peer.get(self.base).status_code, 404)
        self.assertEqual(self.client.post('/api/rooms', json=body).status_code, 422)

    def test_bank_preview_reports_available_fixed_questions_without_calling_ai_or_sharing_keys(self):
        calls=self.provider.calls;path='/api/courses/'+self.course_value['id']+'/room-bank'
        response=self.client.get(path,params={'expected_revision':2});response.raise_for_status();preview=response.json()
        self.assertEqual(preview['available'],4)
        self.assertTrue(all('answer' not in q and 'explanation' not in q for q in preview['questions']))
        self.assertEqual(self.provider.calls,calls)
        self.assertEqual(self.peer().get(path,params={'expected_revision':2}).status_code,404)
        self.assertEqual(self.client.get(path,params={'expected_revision':1}).status_code,409)

    def test_join_code_grants_room_only_and_does_not_enroll_the_course_or_expose_original(self):
        self.create(); peer = self.peer(); self.join(peer)
        self.assertEqual(peer.get('/api/courses/' + self.course_value['id']).status_code, 404)
        source = self.client.get('/api/plans/' + self.course_value['plan_id']).json()['source_id']
        self.assertEqual(peer.get('/api/sources/' + source + '/original').status_code, 404)
        self.assertEqual(peer.get('/api/notebook').json(), [])
        self.assertEqual(self.action('start', peer).status_code, 403)
        self.action('start').raise_for_status()
        value = self.snapshot(peer)
        self.assertNotIn('answer', value['question']); self.assertNotIn('explanation', value['question'])
        self.assertIsNone(value['solution']); self.assertEqual([x['score'] for x in value['scoreboard']], [0,0])
        outsider = self.peer()
        self.assertEqual(outsider.get(self.base + '/results').status_code, 404)

    def test_enrolled_public_course_can_host_but_private_shared_course_cannot_be_reshared_by_learner(self):
        peer=self.peer();course=self.course_value;path='/api/courses/'+course['id']
        publication=self.client.post(path+'/publication-preview',json={'expected_revision':2,'visibility':'public','share_original':False}).json()['publication_id']
        self.client.post('/api/publications/'+publication+'/apply',json={'expected_revision':2}).raise_for_status()
        peer.post(path+'/enroll').raise_for_status()
        body={'course_id':course['id'],'expected_revision':2,'unit_ids':['unit-1'],'question_count':1,'nickname':'Public learner host'}
        response=peer.post('/api/rooms',json=body,headers={'Idempotency-Key':'public-bank'});response.raise_for_status()
        base='/api/rooms/'+response.json()['room_id'];state=peer.get(base).json()
        peer.post(base+'/leave',json={'expected_event_index':state['event_index']},headers={'Idempotency-Key':'leave-public-bank'}).raise_for_status()
        publication=self.client.post(path+'/publication-preview',json={'expected_revision':2,'visibility':'shared','share_original':False}).json()['publication_id']
        self.client.post('/api/publications/'+publication+'/apply',json={'expected_revision':2}).raise_for_status()
        denied=peer.post('/api/rooms',json=body,headers={'Idempotency-Key':'shared-bank'})
        self.assertEqual(denied.status_code,403)

    def test_four_fixed_types_score_by_program_and_results_do_not_change_personal_progress_or_coin(self):
        self.create(); peer = self.peer(); self.join(peer)
        self.finish(peer)
        result = peer.get(self.base + '/results').json()
        self.assertEqual([x['score'] for x in result['scoreboard']], [4, 4])
        self.assertEqual([x['rank'] for x in result['scoreboard']], [1,1])
        self.assertEqual(len(result['questions']), 4)
        self.assertTrue(all(q['correct'] for q in result['questions']))
        self.assertTrue(all(q['sources'] for q in result['questions']))
        course = self.client.get('/api/courses/' + self.course_value['id']).json()
        self.assertFalse(course['content']['units'][1]['unlocked'])
        self.assertEqual(self.client.get('/api/courses/' + self.course_value['id'] + '/history').json(), [])
        self.assertEqual(result['policy']['coin_reward'], 0)

    def test_no_early_result_and_duplicate_or_modified_answer_cannot_increase_points(self):
        self.create(count=1); peer = self.peer(); self.join(peer); self.action('start')
        state = self.snapshot(); before = self.provider.calls
        accepted = self.answer('option-0', snapshot=state, key='once'); accepted.raise_for_status()
        self.assertNotIn('correct', accepted.json())
        self.assertEqual(self.answer('option-0', snapshot=state, key='once').json(), accepted.json())
        self.assertEqual(self.answer('option-1', snapshot=state, key='once').status_code, 409)
        self.assertEqual(self.answer('option-1', snapshot=state, key='changed').status_code, 409)
        self.assertTrue(self.answer('option-0', snapshot=state, key='same-another-key').json()['replayed'])
        value = self.snapshot(peer); self.assertIsNone(value['solution']); self.assertEqual([x['score'] for x in value['scoreboard']], [0,0])
        self.assertEqual(peer.get(self.base + '/results').status_code, 409)
        self.answer('option-1', peer).raise_for_status(); self.action('next')
        result = self.client.get(self.base + '/results').json()
        self.assertEqual(sorted(x['score'] for x in result['scoreboard']), [0,1]); self.assertEqual(self.provider.calls, before)

    def test_own_result_is_revealed_with_the_solution_not_while_the_question_is_open(self):
        self.create(count=1); peer = self.peer(); self.join(peer); self.action('start')
        self.answer('option-0').raise_for_status()
        self.assertIsNone(self.snapshot()['own_result'])
        self.answer('option-1', peer).raise_for_status()
        host, learner = self.snapshot(), self.snapshot(peer)
        self.assertEqual((host['phase'], host['seconds_per_question']), ('question_closed', 5))
        self.assertEqual(host['own_result'], {'correct': True, 'points': 1})
        self.assertEqual(learner['own_result'], {'correct': False, 'points': 0})

    def test_server_deadline_rejects_late_answers_and_automatic_transitions_do_not_restart_the_room(self):
        self.create(count=2); peer = self.peer(); self.join(peer); self.action('start')
        state = self.snapshot(); self.clock.add(5)
        self.assertEqual(self.answer('option-0', peer, state).status_code, 409)
        closed = self.snapshot(); self.assertEqual(closed['phase'], 'question_closed')
        self.assertEqual(closed['closed_count'], 1)
        self.clock.add(8); next_state = self.snapshot()
        self.assertEqual(next_state['phase'], 'question_open'); self.assertEqual(next_state['question_index'], 1)
        self.assertGreater(next_state['event_index'], closed['event_index'])
        self.clock.add(5); self.snapshot(); self.clock.add(8)
        self.assertEqual(self.snapshot()['phase'], 'finished')

    def test_client_cannot_submit_score_correctness_time_or_change_server_duration(self):
        self.create(count=1);peer=self.peer();self.join(peer);self.action('start');state=self.snapshot(peer)
        body={'event_index':state['question_event_index'],'question_id':state['question']['id'],'answer':'option-0'}
        for extra in [{'score':1000},{'correct':True},{'received_at':'yesterday'},{'deadline':9999999999}]:
            response=peer.post(self.base+'/answers',json={**body,**extra},headers={'Idempotency-Key':str(uuid.uuid4())})
            self.assertEqual(response.status_code,422)
        with self.app.state.database.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM quiz_answers WHERE room_id=?',(self.room['room_id'],)).fetchone()[0],0)

    def test_host_disconnect_explicit_leave_and_expiry_have_terminal_states(self):
        self.create(count=1); peer = self.peer(); self.join(peer); self.action('start')
        self.clock.add(61)
        expired = self.snapshot(peer)
        self.assertEqual((expired['phase'], expired['end_reason']), ('cancelled', 'host_disconnected'))
        self.assertEqual(self.client.post(self.base + '/presence').json()['phase'], 'cancelled')
        self.create(count=1); self.join(peer)
        self.action('leave').raise_for_status()
        self.assertEqual(self.snapshot(peer)['end_reason'], 'host_left')
        self.create(count=1); self.join(peer)
        with self.app.state.database.connection(write=True) as db:
            db.execute('UPDATE quiz_rooms SET expires_at=? WHERE id=?', (self.clock().timestamp() + 1, self.room['room_id']))
        self.clock.add(1); self.app.state.rooms.tick()
        self.assertEqual(self.snapshot(peer)['end_reason'], 'room_expired')

    def test_reconnect_after_restart_keeps_question_deadline_and_own_answer(self):
        self.create(count=1); peer = self.peer(); self.join(peer); self.action('start')
        self.answer('option-0', peer).raise_for_status(); before = self.snapshot(peer)
        app = create_app(self.app.state.database.path, self.temp.name + '/sources', provider=self.provider, clock=self.clock, economy_enabled=False)
        with TestClient(app, base_url='http://127.0.0.1') as connected:
            connected.cookies.update(dict(peer.cookies))
            after = connected.get(self.base).json()
            for key in ['question','own_answer','question_index','deadline','event_index','course_revision']:
                self.assertEqual(after[key], before[key])

    def test_background_maintenance_closes_a_disconnected_host_without_an_http_poll(self):
        self.create(count=1);peer=self.peer();self.join(peer);self.action('start')
        with TestClient(self.app,base_url='http://127.0.0.1'):
            self.clock.add(61)
            limit=time.monotonic()+3
            while time.monotonic()<limit:
                with self.app.state.database.connection() as db:
                    phase=db.execute('SELECT phase FROM quiz_rooms WHERE id=?',(self.room['room_id'],)).fetchone()[0]
                if phase=='cancelled':break
                time.sleep(.1)
            self.assertEqual(phase,'cancelled')

    def test_expired_auth_cookie_cannot_read_snapshot_results_or_event_stream(self):
        self.create(count=1);peer=self.peer();self.join(peer)
        actor=peer.post('/api/session').json()['id']
        with self.app.state.database.connection(write=True) as db:
            db.execute('UPDATE auth_sessions SET expires_at=0 WHERE user_id=?',(actor,))
        for suffix in ['', '/results', '/events?once=true']:
            self.assertEqual(peer.get(self.base+suffix).status_code,401)

    def test_state_actions_are_versioned_and_idempotent(self):
        self.create(count=2); peer = self.peer(); self.join(peer)
        version = self.snapshot()['event_index']
        first = self.action('start', version=version, key='start-once'); first.raise_for_status()
        self.assertEqual(self.action('start', version=version, key='start-once').json(), first.json())
        self.assertEqual(self.action('close-question', version=version).status_code, 409)
        self.action('close-question').raise_for_status()
        version = self.snapshot()['event_index']
        first = self.action('next', version=version, key='next-once'); first.raise_for_status()
        self.assertEqual(self.action('next', version=version, key='next-once').json(), first.json())
        self.assertEqual(self.snapshot()['question_index'], 1)

    def test_concurrent_answer_retries_insert_only_one_answer(self):
        self.create(count=1); peer = self.peer(); self.join(peer); self.action('start'); state = self.snapshot(peer)
        async def scenario():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://127.0.0.1', cookies=peer.cookies) as client:
                body = {'event_index': state['question_event_index'], 'question_id': state['question']['id'], 'answer': 'option-0'}
                responses = await asyncio.gather(*(client.post(self.base + '/answers', json=body, headers={'Idempotency-Key': 'race-' + str(i)}) for i in range(2)))
                self.assertEqual([x.status_code for x in responses], [200,200])
        asyncio.run(scenario())
        with self.app.state.database.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM quiz_answers WHERE room_id=?', (self.room['room_id'],)).fetchone()[0], 1)

    def test_sse_is_private_and_reconnect_returns_snapshot_without_open_answers(self):
        self.create(count=1); peer = self.peer(); self.join(peer); self.action('start'); version = self.snapshot()['event_index']
        response = peer.get(self.base + '/events?once=true', headers={'Last-Event-ID': str(version)})
        response.raise_for_status();self.assertIn('text/event-stream', response.headers['content-type'])
        self.assertIn('event: snapshot', response.text)
        event = json.loads(next(x[6:] for x in response.text.splitlines() if x.startswith('data: ')))
        self.assertEqual(event['event_index'], version); self.assertIsNone(event['solution'])
        self.assertNotIn('answer', event['question'])
        self.assertEqual(self.peer().get(self.base + '/events?once=true').status_code, 404)
        self.assertEqual(peer.get(self.base + '/events?once=true', headers={'Last-Event-ID':'999'}).status_code, 409)

    def test_running_room_blocks_ai_editor_and_old_solution_apis_then_allows_private_post_room_help(self):
        self.create(count=1); peer = self.peer(); self.join(peer); self.action('start'); state = self.snapshot(); qid=state['question']['id']
        calls = self.provider.calls
        self.assertEqual(self.client.post('/api/courses/' + self.course_value['id'] + '/chat', json={'unit_id':'unit-1','message':'hint'}).status_code, 403)
        self.assertEqual(self.client.get('/api/courses/' + self.course_value['id'] + '/editor').status_code, 200)
        self.assertEqual(peer.post(self.base + '/questions/' + qid + '/chat', json={'question_id':qid,'message':'hint'}).status_code, 403)
        self.assertEqual(self.provider.calls, calls)
        self.answer('option-0'); self.answer('option-1', peer); self.action('next')
        response=peer.post(self.base + '/questions/' + qid + '/chat',json={'question_id':qid,'message':'Explain my answer'})
        response.raise_for_status()
        self.assertEqual(peer.get('/api/jobs/' + response.json()['job_id']).json()['status'], 'succeeded')
        self.assertEqual([m['role'] for m in peer.get(self.base + '/questions/' + qid + '/chat').json()], ['user','assistant'])
        self.assertEqual(self.client.get(self.base + '/questions/' + qid + '/chat').json(), [])
        self.assertEqual(self.provider.calls, calls + 1)
        self.assertIn('"normalized_answer": "B"',self.provider.instructions[-1])
        self.assertIn('"correct": false',self.provider.instructions[-1])

    def test_creator_manual_edit_during_running_room_does_not_change_room_question_revision(self):
        self.create(count=1); peer = self.peer(); self.join(peer)
        self.action('start')
        question = copy.deepcopy(self.course_value['content']['units'][0]['data']['questions'][0]); question['answer']='B'
        proposal=self.client.post('/api/courses/'+self.course_value['id']+'/proposals',json={'expected_revision':2,'unit_id':'unit-1','target':'question','index':0,'request':'Changed key after room pin','replacement':question}).json()['proposal_id']
        self.client.post('/api/proposals/'+proposal+'/apply',json={'expected_revision':2}).raise_for_status()
        self.answer('option-0');self.answer('option-0',peer);self.action('next')
        result=peer.get(self.base+'/results').json()
        self.assertEqual(result['course_revision'],2); self.assertTrue(result['questions'][0]['correct'])
        self.assertEqual(self.client.get('/api/courses/'+self.course_value['id']).json()['revision'],3)

    def test_roster_change_does_not_reject_other_on_time_answers(self):
        self.create(count=1); peer=self.peer(); other=self.peer();self.join(peer);self.join(other,'Other')
        self.action('start');state=self.snapshot()
        self.action('leave',other).raise_for_status()
        self.assertNotEqual(self.snapshot()['event_index'],state['event_index'])
        self.answer('option-0',snapshot=state).raise_for_status()
        self.answer('option-0',peer,snapshot=state).raise_for_status()
        self.assertEqual(self.snapshot()['phase'],'question_closed')

    def test_known_bad_question_is_not_opened_or_scored_after_room_was_pinned(self):
        self.create(count=1);peer=self.peer();self.join(peer)
        with self.app.state.database.connection(write=True) as db:
            bank=json.loads(db.execute('SELECT bank_json FROM quiz_rooms WHERE id=?',(self.room['room_id'],)).fetchone()[0])
            db.execute('INSERT INTO question_review_flags VALUES (?,?,?,?,?)',(self.course_value['id'],bank[0]['question_revision_id'],'needs_review','Ambiguous answer found later',self.clock().isoformat()))
        self.action('start').raise_for_status()
        state=self.snapshot(peer)
        self.assertEqual(state['phase'],'cancelled');self.assertEqual(state['end_reason'],'question_needs_review')
        self.assertIsNone(state['question']);self.assertEqual(state['closed_count'],0)

    def test_current_question_flag_ends_unscored_round_without_altering_previous_published_score(self):
        self.create(count=2);peer=self.peer();self.join(peer);self.action('start')
        self.answer('option-0');self.answer('option-0',peer);self.action('next')
        self.answer('62')
        with self.app.state.database.connection(write=True) as db:
            bank=json.loads(db.execute('SELECT bank_json FROM quiz_rooms WHERE id=?',(self.room['room_id'],)).fetchone()[0])
            db.execute('INSERT INTO question_review_flags VALUES (?,?,?,?,?)',(self.course_value['id'],bank[1]['question_revision_id'],'needs_review','Needs source review',self.clock().isoformat()))
        state=self.snapshot(peer)
        self.assertEqual(state['phase'],'cancelled');self.assertEqual(state['closed_count'],1)
        self.assertEqual([x['score'] for x in state['scoreboard']],[1,1])
        self.assertIsNotNone(state['reference_warning'])

    def test_post_room_help_keeps_the_pinned_content_language(self):
        original_preferences=self.preferences
        self.preferences=lambda source:{**original_preferences(source),'language':'en'}
        self.course_value=self.course()
        original_generate=self.provider.generate
        async def english(schema,instruction,fragments):
            if schema is ChatReply:
                self.provider.calls+=1;self.provider.instructions.append(instruction)
                return {'text':'The fixed answer follows the provided source.','source_refs':[f['id'] for f in fragments],'needs_more_source':False}
            return await original_generate(schema,instruction,fragments)
        self.provider.generate=english
        self.create(count=1);peer=self.peer();self.join(peer);self.finish(peer,['option-0'])
        qid=self.snapshot()['question']['id']
        response=peer.post(self.base+'/questions/'+qid+'/chat',json={'question_id':qid,'message':'Explain'})
        response.raise_for_status()
        result=peer.get('/api/jobs/'+response.json()['job_id']).json()
        self.assertEqual(result['status'],'succeeded')
        self.assertIn('OUTPUT LANGUAGE: ENGLISH',self.provider.instructions[-1])

    def test_old_room_results_and_help_are_withheld_while_playing_the_same_course(self):
        self.create(count=1);peer=self.peer();self.join(peer);self.finish(peer,['option-0'])
        previous=self.base
        self.create(count=1);self.join(peer);self.action('start')
        self.assertEqual(peer.get(previous).status_code,403)
        self.assertEqual(peer.get(previous+'/results').status_code,403)
        self.assertEqual(peer.get(previous+'/questions/unit-1:q0/chat').status_code,403)

    def test_room_capacity_nicknames_join_bruteforce_and_no_late_join(self):
        self.app.state.rooms.policy['max_players']=2
        self.create(count=1); peer=self.peer();self.join(peer)
        extra=self.peer()
        self.assertEqual(extra.post('/api/rooms/join',json={'code':self.room['join_code'],'nickname':'Extra'}).status_code,409)
        self.action('start')
        self.assertEqual(extra.post('/api/rooms/join',json={'code':self.room['join_code'],'nickname':'Extra'}).status_code,409)
        for _ in range(21):response=extra.post('/api/rooms/join',json={'code':'BADCODE1','nickname':'Guess'})
        self.assertEqual(response.status_code,429)
