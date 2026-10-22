"""Course memory reaches every chat/help prompt; section help tutors on the whole lesson."""
from fastapi.testclient import TestClient
from test_slice import SliceFixture


class CourseMemoryTests(SliceFixture):
    def setUp(self):
        super().setUp()
        self.value = self.course()
        self.base = '/api/courses/' + self.value['id']

    def save(self, notes, version):
        return self.client.put(self.base + '/memory', json={'notes': notes, 'expected_version': version})

    def test_notes_are_versioned_per_learner_and_wrong_answers_are_remembered(self):
        empty = self.client.get(self.base + '/memory').json()
        self.assertEqual((empty['notes'], empty['version'], empty['struggles']), ('', 0, []))
        self.assertEqual(empty['course']['subject'], 'Mạng máy tính')
        self.assertEqual(self.save('Giải thích bằng ví dụ đời thường', 0).json()['version'], 1)
        self.assertEqual(self.save('Ghi đè từ tab cũ', 0).status_code, 409)
        session = self.client.post(self.base + '/sessions', json={'expected_revision': 2, 'unit_id': 'unit-1'}).json()
        wrong = session['questions'][0]
        self.client.post(f"/api/sessions/{session['id']}/answers", json={'item_id': wrong['id'], 'answer': 'option-1'}).raise_for_status()
        memory = self.client.get(self.base + '/memory').json()
        self.assertEqual(memory['notes'], 'Giải thích bằng ví dụ đời thường')
        self.assertEqual([s['prompt'] for s in memory['struggles']], [wrong['prompt']])
        with TestClient(self.app, base_url='http://127.0.0.1') as stranger:
            stranger.post('/api/session')
            self.assertIn(stranger.get(self.base + '/memory').status_code, {403, 404})
            self.assertIn(stranger.put(self.base + '/memory', json={'notes': 'x', 'expected_version': 0}).status_code, {403, 404})

    def test_chat_and_question_help_receive_the_memory_but_not_tutor_rules(self):
        self.save('Mình hay nhầm /26 với /27', 0).raise_for_status()
        self.job(self.client.post(self.base + '/chat', json={'unit_id': 'unit-1', 'message': 'Broadcast là gì?'}))
        self.assertIn('Mình hay nhầm /26 với /27', self.provider.instructions[-1])
        self.assertIn('course_memory', self.provider.instructions[-1])
        session = self.client.post(self.base + '/sessions', json={'expected_revision': 2, 'unit_id': 'unit-1'}).json()
        q = session['questions'][0]
        thread = self.client.post(f"/api/sessions/{session['id']}/items/{q['id']}/help").json()['thread_id']
        self.job(self.client.post(f'/api/help/threads/{thread}/actions', json={'action': 'ask', 'message': 'Vì sao?'}))
        prompt = self.provider.instructions[-1]
        self.assertIn('Mình hay nhầm /26 với /27', prompt)
        self.assertNotIn('Ví dụ minh họa', prompt)

    def test_tutor_style_is_one_per_learner_and_joins_every_chat_and_help_prompt(self):
        empty = self.client.get('/api/tutor-style').json()
        self.assertEqual((empty['persona'], empty['emphasis'], empty['version']), ('', '', 0))
        saved = self.client.put('/api/tutor-style', json={'persona': ' Gia sư kiên nhẫn, nói như bạn cùng lớp ', 'emphasis': 'Lỗi hay gặp', 'expected_version': 0}).json()
        self.assertEqual((saved['persona'], saved['version']), ('Gia sư kiên nhẫn, nói như bạn cùng lớp', 1))
        self.assertEqual(self.client.put('/api/tutor-style', json={'persona': 'x', 'emphasis': '', 'expected_version': 0}).status_code, 409)
        self.assertEqual(self.client.put('/api/tutor-style', json={'persona': 'x' * 301, 'emphasis': '', 'expected_version': 1}).status_code, 422)
        self.job(self.client.post(self.base + '/chat', json={'unit_id': 'unit-1', 'message': 'Broadcast là gì?'}))
        prompt = self.provider.instructions[-1]
        self.assertIn('Gia sư kiên nhẫn, nói như bạn cùng lớp', prompt)
        self.assertIn('Lỗi hay gặp', prompt)
        self.assertIn('tutor_style', prompt)
        session = self.client.post(self.base + '/sessions', json={'expected_revision': 2, 'unit_id': 'unit-1'}).json()
        thread = self.client.post(f"/api/sessions/{session['id']}/items/{session['questions'][0]['id']}/help").json()['thread_id']
        self.job(self.client.post(f'/api/help/threads/{thread}/actions', json={'action': 'ask', 'message': 'Vì sao?'}))
        self.assertIn('Gia sư kiên nhẫn, nói như bạn cùng lớp', self.provider.instructions[-1])
        # Another learner neither sees nor gets this style.
        with TestClient(self.app, base_url='http://127.0.0.1') as stranger:
            stranger.post('/api/session')
            self.assertEqual(stranger.get('/api/tutor-style').json()['persona'], '')

    def test_section_help_sees_every_lesson_source_and_what_was_taught(self):
        unit = self.value['content']['units'][0]
        thread = self.client.post(self.base + '/units/unit-1/sections/0/help', json={'expected_revision': 2}).json()['thread_id']
        seen = []
        generate = self.provider.generate

        async def spy(schema, instruction, fragments):
            seen.append([f['id'] for f in fragments])
            return await generate(schema, instruction, fragments)

        self.provider.generate = spy
        self.job(self.client.post(f'/api/help/threads/{thread}/actions', json={'action': 'ask', 'message': 'Cho ví dụ đời thường'}))
        prompt = self.provider.instructions[-1]
        self.assertEqual(sorted(seen[-1]), sorted(unit['source_refs']))
        self.assertIn('Ví dụ minh họa', prompt)
        self.assertIn(unit['data']['sections'][0]['text'], prompt)
