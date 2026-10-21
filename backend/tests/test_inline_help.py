import asyncio
import httpx
from fastapi.testclient import TestClient
from test_slice import SliceFixture
from study_backend.inline_help import context_history


class InlineHelpTests(SliceFixture):
    def setUp(self):
        super().setUp()
        self.course_value = self.course()
        self.base = '/api/courses/' + self.course_value['id']
        self.session = self.client.post(self.base + '/sessions', json={'expected_revision': 2, 'unit_id': 'unit-1'}).json()

    def open_thread(self, question=0):
        q = self.session['questions'][question]
        response = self.client.post(f"/api/sessions/{self.session['id']}/items/{q['id']}/help")
        response.raise_for_status()
        return response.json()['thread_id']

    def action(self, thread, action, **extra):
        return self.client.post('/api/help/threads/' + thread + '/actions', json={'action': action, **extra})

    def test_before_answer_explain_and_reveal_are_saved_free_and_assisted_not_fake_answers(self):
        thread = self.open_thread();calls = self.provider.calls
        safe = self.client.get('/api/help/threads/' + thread).json()
        self.assertNotIn('answer', safe['context']['question'])
        self.assertIsNone(safe['student']['answer']);self.assertFalse(safe['student']['submitted'])
        first = self.action(thread, 'explain');first.raise_for_status()
        self.assertEqual(first.json()['reply']['text'], 'Giải thích từ nguồn test')
        self.assertFalse(first.json()['ai_called'])
        self.assertTrue(self.action(thread, 'explain').json()['cached'])
        self.assertEqual(self.action(thread, 'reveal').json()['reply']['reference'], 'A')
        q = self.session['questions'][0]
        self.assertEqual(self.client.get('/api/sessions/' + self.session['id']).json()['answers'], {})
        self.client.post('/api/sessions/' + self.session['id'] + '/answers', json={'item_id': q['id'], 'answer': 'option-1'}).raise_for_status()
        self.assertTrue(self.client.get('/api/sessions/' + self.session['id']).json()['answers'][q['id']]['assisted'])
        self.assertEqual(self.provider.calls, calls)

    def test_fixed_hint_progress_and_draft_are_scoped_per_question_and_not_global_chat(self):
        first = self.open_thread();second = self.open_thread(1)
        q = self.session['questions'][0]
        self.assertEqual(self.client.post(f"/api/sessions/{self.session['id']}/items/{q['id']}/help").json()['thread_id'], first)
        self.assertEqual(self.action(first, 'hint').json()['reply']['eliminated_option_ids'], ['option-1'])
        self.assertTrue(self.action(first, 'hint').json()['cached'])
        draft = '/api/help/threads/' + first + '/draft'
        self.client.put(draft, json={'text': 'Why is B wrong?', 'expected_version': 0}).raise_for_status()
        self.assertEqual(self.client.put(draft, json={'text': 'Overwrite', 'expected_version': 0}).status_code, 409)
        self.assertEqual(self.client.get('/api/help/threads/' + second).json()['draft']['text'], '')
        self.assertEqual(self.client.get('/api/help/threads/' + second).json()['messages'], [])
        self.assertEqual(self.client.get(self.base + '/chat').json(), [])
        self.assertEqual(self.client.get('/api/help/threads/' + first).json()['draft']['text'], 'Why is B wrong?')

    def test_structured_hints_for_all_five_types_use_saved_keys_not_ai(self):
        calls = self.provider.calls
        expected = [('eliminated_option_ids', ['option-1']), ('prefix', '6'), ('pairs', {'left-0': 'option-0'}), ('ordered_option_ids', ['option-0']), ('criteria', ['Tự đối chiếu'])]
        for index, (field, value) in enumerate(expected):
            with self.subTest(kind=self.session['questions'][index]['kind']):
                thread = self.open_thread(index)
                reply = self.action(thread, 'hint').json()
                self.assertFalse(reply['ai_called']);self.assertEqual(reply['reply'][field], value)
                self.assertEqual(self.action(thread, 'reveal').status_code, 200)
                self.assertEqual(self.action(thread, 'explain').status_code, 200)
        self.assertEqual(self.provider.calls, calls)
        self.assertEqual(self.client.get('/api/sessions/' + self.session['id']).json()['answers'], {})

    def test_ai_context_keeps_latest_complete_messages_with_a_bounded_window(self):
        values = [{'role': 'user', 'action': 'ask', 'content': {'text': f'request-{i} ' + 'x' * 1800, 'student': {'draft': 'not duplicated'}}} for i in range(12)]
        chosen = context_history(values)
        self.assertIn('request-11', chosen[-1]['content']['text'])
        self.assertNotIn('request-0 ', str(chosen))
        self.assertLessEqual(len(str(chosen)), 6000)
        self.assertNotIn('student', str(chosen))
        self.assertEqual(len(values), 12)

    def test_ai_followup_gets_pinned_question_student_answer_and_history_with_separate_receipt(self):
        first = self.open_thread();second = self.open_thread(1)
        q = self.session['questions'][0]
        self.client.post('/api/sessions/' + self.session['id'] + '/answers', json={'item_id': q['id'], 'answer': 'option-1'})
        response = self.client.post('/api/help/threads/' + first + '/actions', json={'action': 'ask', 'message': 'Why my selected option?'}, headers={'Idempotency-Key': 'same-help'})
        self.job(response)
        prompt = self.provider.instructions[-1]
        self.assertIn(q['prompt'], prompt);self.assertIn('option-1', prompt);self.assertIn('Không hỏi lại môn', prompt)
        self.assertNotIn(self.session['questions'][1]['prompt'], prompt)
        calls = self.provider.calls
        self.assertEqual(self.client.post('/api/help/threads/' + first + '/actions', json={'action': 'ask', 'message': 'Why my selected option?'}, headers={'Idempotency-Key': 'same-help'}).json(), response.json())
        self.assertEqual(self.provider.calls, calls)
        self.assertEqual(self.client.get('/api/help/threads/' + second).json()['messages'], [])
        self.assertEqual(self.client.get(self.base + '/chat').json(), [])

    def test_creator_edit_does_not_change_pinned_context_or_old_key_warning(self):
        thread = self.open_thread();q = self.session['questions'][0]
        self.client.post(self.base + '/question-reports', json={'expected_revision': 2, 'unit_id': 'unit-1', 'item_id': q['id'], 'reason': 'Reference might be wrong'}).raise_for_status()
        replacement = {**self.course_value['content']['units'][0]['data']['questions'][0], 'answer': 'B'}
        proposal = self.client.post(self.base + '/proposals', json={'expected_revision': 2, 'unit_id': 'unit-1', 'target': 'question', 'index': 0, 'request': 'correct key', 'replacement': replacement}).json()['proposal_id']
        self.client.post('/api/proposals/' + proposal + '/apply', json={'expected_revision': 2}).raise_for_status()
        old = self.client.get('/api/help/threads/' + thread).json()
        self.assertEqual(old['revision'], 2)
        self.assertEqual(old['reference_warning']['state'], 'needs_review')
        reply = self.action(thread, 'explain').json()['reply']
        self.assertEqual(reply['reference'], 'A')
        self.assertFalse(reply['reference_warning']['reference_is_verified'])

    def test_unsubmitted_selection_is_context_not_a_graded_answer(self):
        thread = self.open_thread();q = self.session['questions'][0]
        self.client.put('/api/sessions/' + self.session['id'] + '/draft', json={'item_id': q['id'], 'answer': 'option-1', 'expected_version': 0}).raise_for_status()
        snapshot = self.client.get('/api/help/threads/' + thread).json()
        self.assertEqual(snapshot['student']['draft'], 'option-1')
        self.assertEqual(snapshot['student']['draft_display'], q['options'][1])
        self.assertFalse(snapshot['student']['submitted'])
        self.job(self.action(thread, 'ask', message='Is this selected option reasonable?'))
        self.assertIn('"draft": "option-1"', self.provider.instructions[-1])
        self.assertEqual(self.client.get('/api/sessions/' + self.session['id']).json()['answers'], {})

    def test_save_help_note_uses_server_message_and_does_not_duplicate_or_cross_thread(self):
        first = self.open_thread();second = self.open_thread(1)
        self.action(first, 'explain')
        message = self.client.get('/api/help/threads/' + first).json()['messages'][0]
        path = '/api/help/threads/' + first + '/notebook'
        result = self.client.post(path, json={'message_id': message['id']});result.raise_for_status()
        note = result.json()
        self.assertEqual(note['label'], 'ai')
        self.assertIn('Giải thích từ nguồn test', note['body'])
        self.assertEqual(self.client.post(path, json={'message_id': message['id']}).json()['id'], note['id'])
        self.assertEqual(self.client.post('/api/help/threads/' + second + '/notebook', json={'message_id': message['id']}).status_code, 404)
        with TestClient(self.app, base_url='http://127.0.0.1') as peer:
            peer.post('/api/session')
            self.assertEqual(peer.post(path, json={'message_id': message['id']}).status_code, 404)
        self.client.delete('/api/notebook/' + note['id'])
        self.assertEqual(self.client.post(path, json={'message_id': message['id']}).status_code, 409)
        self.client.post('/api/notebook/' + note['id'] + '/restore')
        self.assertEqual(self.client.post(path, json={'message_id': message['id']}).json()['id'], note['id'])

    def test_exam_blocks_thread_read_fixed_actions_new_ai_and_old_job_results(self):
        thread = self.open_thread();job = self.action(thread, 'ask', message='A hint')
        self.job(job)
        exam = self.client.post(self.base + '/sessions', json={'expected_revision': 2, 'unit_id': 'unit-1', 'exercise': 'test'}).json()
        self.assertEqual(self.client.get('/api/help/threads/' + thread).status_code, 403)
        self.assertEqual(self.action(thread, 'explain').status_code, 403)
        self.assertEqual(self.action(thread, 'ask', message='Bypass?').status_code, 403)
        self.assertIsNone(self.client.get('/api/jobs/' + job.json()['job_id']).json()['result'])
        self.client.post('/api/sessions/' + exam['id'] + '/cancel')
        self.assertEqual(self.client.get('/api/help/threads/' + thread).status_code, 200)
        self.assertEqual(self.client.post(f"/api/sessions/{exam['id']}/items/{exam['questions'][0]['id']}/help").status_code, 200)
        with TestClient(self.app, base_url='http://127.0.0.1') as peer:
            peer.post('/api/session')
            self.assertEqual(peer.get('/api/help/threads/' + thread).status_code, 404)
            self.assertEqual(peer.put('/api/help/threads/' + thread + '/draft', json={'text': 'intrude', 'expected_version': 0}).status_code, 404)

    def test_section_explanation_caches_and_different_sections_do_not_share_history(self):
        path = self.base + '/units/unit-1/sections/0/help'
        thread = self.client.post(path, json={'expected_revision': 2}).json()['thread_id']
        calls = self.provider.calls
        self.job(self.action(thread, 'explain'))
        self.assertTrue(self.action(thread, 'explain').json()['cached'])
        self.assertEqual(self.provider.calls, calls + 1)
        self.assertEqual(self.client.post(path, json={'expected_revision': 1}).status_code, 409)
        self.assertEqual(self.client.post(self.base + '/units/unit-1/sections/99/help', json={'expected_revision': 2}).status_code, 404)

    def test_paid_followup_quote_precedes_message_and_keeps_draft_on_failure(self):
        thread = self.open_thread();self.app.state.economy.enabled = True
        path = '/api/help/threads/' + thread
        self.client.put(path + '/draft', json={'text': 'Please explain my thinking', 'expected_version': 0})
        body = {'action': 'ask', 'message': 'Please explain my thinking'}
        quoted = self.client.post(path + '/actions', json=body, headers={'Idempotency-Key': 'quoted-help'})
        self.assertEqual(quoted.status_code, 402)
        self.assertEqual(self.client.get(path).json()['messages'], [])
        self.assertEqual(self.client.get(path).json()['draft']['text'], body['message'])
        async def unavailable(*args):raise RuntimeError('Local model unavailable')
        self.provider.generate = unavailable
        response = self.client.post(path + '/actions', json=body, headers={'Idempotency-Key': 'quoted-help', 'Coin-Quote-Id': quoted.json()['detail']['quote_id']})
        self.assertEqual(self.client.get('/api/jobs/' + response.json()['job_id']).json()['status'], 'failed')
        self.assertEqual(self.client.get('/api/wallet').json()['available'], 20)
        self.assertEqual(self.client.get(path).json()['draft']['text'], body['message'])

    def test_insufficient_source_keeps_request_and_releases_coin(self):
        thread = self.open_thread();self.app.state.economy.enabled = True
        path = '/api/help/threads/' + thread
        body = {'action': 'ask', 'message': 'A topic beyond this source'}
        self.client.put(path + '/draft', json={'text': body['message'], 'expected_version': 0})
        async def insufficient(*args):
            return {'text': 'Nguồn hiện tại chưa đủ để trả lời.', 'source_refs': [], 'needs_more_source': True}
        self.provider.generate = insufficient
        quote = self.client.post(path + '/actions', json=body, headers={'Idempotency-Key': 'insufficient-inline'}).json()['detail']
        response = self.client.post(path + '/actions', json=body, headers={'Idempotency-Key': 'insufficient-inline', 'Coin-Quote-Id': quote['quote_id']})
        result = self.job(response)
        self.assertTrue(result['needs_more_source'])
        self.assertEqual(self.client.get('/api/wallet').json()['available'], 20)
        self.assertEqual(self.client.get(path).json()['draft']['text'], body['message'])

    def test_response_in_flight_remains_on_original_question_after_moving_to_next(self):
        first = self.open_thread();second = self.open_thread(1)
        self.client.put('/api/help/threads/' + first + '/draft', json={'text': 'Explain this question', 'expected_version': 0}).raise_for_status()
        async def scenario():
            started, release = asyncio.Event(), asyncio.Event()
            generate = self.provider.generate
            async def slow(*args):
                started.set();await release.wait();return await generate(*args)
            self.provider.generate = slow
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://127.0.0.1', cookies=self.client.cookies) as client:
                pending = asyncio.create_task(client.post('/api/help/threads/' + first + '/actions', json={'action': 'ask', 'message': 'Explain this question'}))
                await asyncio.wait_for(started.wait(), 2)
                await client.put('/api/help/threads/' + first + '/draft', json={'text': 'A newer follow-up while waiting', 'expected_version': 1})
                await client.put('/api/help/threads/' + second + '/draft', json={'text': 'My next question', 'expected_version': 0})
                second_view = (await client.get('/api/help/threads/' + second)).json()
                self.assertEqual(second_view['messages'], [])
                release.set();await pending
                after = (await client.get('/api/help/threads/' + second)).json()
                self.assertEqual(after['messages'], [])
                self.assertEqual(after['draft']['text'], 'My next question')
                self.assertEqual((await client.get('/api/help/threads/' + first)).json()['messages'][-1]['role'], 'assistant')
                self.assertEqual((await client.get('/api/help/threads/' + first)).json()['draft']['text'], 'A newer follow-up while waiting')
        asyncio.run(scenario())
