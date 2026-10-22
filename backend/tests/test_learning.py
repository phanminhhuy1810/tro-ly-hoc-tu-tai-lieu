import copy
from fastapi.testclient import TestClient

from test_slice import SliceFixture


class LearningTests(SliceFixture):
    def test_session_replay_is_one_attempt_and_key_cannot_change_scope(self):
        course = self.course()
        path = f"/api/courses/{course['id']}/sessions"
        body = {"expected_revision": course['revision'], "unit_id": 'unit-1'}
        headers = {'Idempotency-Key':'one-practice-intent'}
        first = self.client.post(path, json=body, headers=headers).json()
        self.assertEqual(self.client.post(path, json=body, headers=headers).json(), first)
        result = self.answer_all(first)
        self.assertEqual(self.client.post(path, json=body, headers=headers).json(), first)
        self.assertEqual(self.client.post(path, json={**body, 'exercise':'test'}, headers=headers).status_code, 409)
        history = self.client.get(f"/api/courses/{course['id']}/history").json()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['result'], result)

    def test_exam_cannot_reveal_answer_from_old_session_or_generation_partial(self):
        course = self.course()
        practice = self.begin(course)
        self.answer_all(practice)
        self.assertIsNotNone(self.client.get(f"/api/sessions/{practice['id']}").json()['answers']['unit-1:q0']['feedback'])
        exam = self.begin(course, exercise='test')
        previous = self.client.get(f"/api/sessions/{practice['id']}").json()
        self.assertTrue(previous['feedback_deferred'])
        self.assertIsNone(previous['answers']['unit-1:q0']['feedback'])
        with self.app.state.database.connection() as db:
            job = db.execute("SELECT id FROM jobs WHERE task='lesson' ORDER BY created_at DESC LIMIT 1").fetchone()
        partial = self.client.get('/api/jobs/'+job['id']).json()
        self.assertTrue(partial['feedback_deferred'])
        for draft in partial['partial']['questions'].values():
            if draft['question']:
                self.assertNotIn('answer', draft['question'])
                self.assertNotIn('explanation', draft['question'])
        self.answer_all(exam)
        self.assertIsNotNone(self.client.get(f"/api/sessions/{practice['id']}").json()['answers']['unit-1:q0']['feedback'])

    def begin(self, course, **options):
        response = self.client.post(f"/api/courses/{course['id']}/sessions", json={"expected_revision": course["revision"], "unit_id": "unit-1", **options})
        response.raise_for_status()
        return response.json()

    def answer_all(self, session, wrong=False):
        for q in session["questions"]:
            choices = q["payload"]["options"]
            if q["kind"] == "mcq": answer = choices[1 if wrong else 0]["id"]
            elif q["kind"] == "cloze": answer = "0" if wrong else "62.0"
            elif q["kind"] == "matching": answer = {"left-1": "option-0" if wrong else "option-1", "left-0": "option-1" if wrong else "option-0"}
            elif q["kind"] == "ordering": answer = ["option-1", "option-0"] if wrong else ["option-0", "option-1"]
            else: answer = "Tự đối chiếu"
            self.client.post(f"/api/sessions/{session['id']}/answers", json={"item_id": q["id"], "answer": answer}).raise_for_status()
        response = self.client.post(f"/api/sessions/{session['id']}/complete"); response.raise_for_status()
        return response.json()

    def test_payload_ids_grade_regardless_of_matching_display_order(self):
        course = self.course(); session = self.begin(course)
        self.assertNotIn("answer", session["questions"][0])
        self.assertNotIn("answer", self.client.get(f"/api/courses/{course['id']}").json()["content"]["units"][0]["data"]["questions"][0])
        result = self.answer_all(session)
        self.assertEqual((result["score"], result["fixed_total"], result["self_review_count"]), (4, 4, 1))

    def test_exam_hides_feedback_until_complete_and_blocks_editor_help_ai(self):
        course = self.course(); session = self.begin(course, mode="practice", exercise="test")
        q = session["questions"][0]
        response = self.client.post(f"/api/sessions/{session['id']}/answers", json={"item_id": q["id"], "answer": "option-1"})
        self.assertEqual(response.json(), {"accepted": True, "item_id": q["id"]})
        self.assertIsNone(self.client.get(f"/api/sessions/{session['id']}").json()["answers"][q["id"]]["feedback"])
        self.assertEqual(self.client.get(f"/api/courses/{course['id']}/editor").status_code, 403)
        self.assertEqual(self.client.post(f"/api/sessions/{session['id']}/items/{q['id']}/solution").status_code, 403)
        calls = self.provider.calls
        self.assertEqual(self.client.post(f"/api/courses/{course['id']}/chat", json={"unit_id": "unit-1", "message": "Tell answer"}).status_code, 403)
        self.assertEqual(self.provider.calls, calls)
        # Exam answers may be revised before the final submission.
        result = self.answer_all(session)
        self.assertEqual(result["score"], 4)
        restored = self.client.get(f"/api/sessions/{session['id']}").json()
        self.assertTrue(restored["answers"][q["id"]]["feedback"]["correct"])

    def test_draft_resume_is_ungraded_private_and_rejects_stale_tab(self):
        course = self.course(); session = self.begin(course)
        q = session["questions"][1]
        draft = {"item_id": q["id"], "answer": "6", "expected_version": 0}
        self.assertFalse(self.client.put(f"/api/sessions/{session['id']}/draft", json=draft).json()["graded"])
        self.assertEqual(self.client.put(f"/api/sessions/{session['id']}/draft", json=draft).status_code, 409)
        resumed = self.client.get(f"/api/sessions/{session['id']}").json()
        self.assertEqual(resumed["drafts"][q["id"]]["answer"], "6")
        self.assertEqual(resumed["answers"], {})
        resume = self.client.get('/api/resume').json()[0]
        self.assertEqual(resume["position"]["item_id"], q["id"])
        self.client.post(f"/api/sessions/{session['id']}/answers", json={"item_id": q["id"], "answer": "62"}).raise_for_status()
        self.assertEqual(self.client.get(f"/api/sessions/{session['id']}").json()["drafts"], {})
        with TestClient(self.app, base_url="http://127.0.0.1") as outsider:
            outsider.post('/api/session')
            self.assertEqual(outsider.get(f"/api/sessions/{session['id']}").status_code, 404)
            self.assertEqual(outsider.get('/api/resume').json(), [])

    def test_saved_solution_calls_no_ai_and_flags_assistance_before_submission(self):
        course = self.course(); session = self.begin(course); q = session["questions"][0]
        calls = self.provider.calls
        help_value = self.client.post(f"/api/sessions/{session['id']}/items/{q['id']}/solution").json()
        self.assertFalse(help_value["ai_called"]); self.assertEqual(self.provider.calls, calls)
        result = self.answer_all(session)
        self.assertEqual(result["assisted_count"], 1)
        # Reading another explanation after submission must not rewrite history.
        other_q = session["questions"][1]
        self.client.post(f"/api/sessions/{session['id']}/items/{other_q['id']}/solution").raise_for_status()
        self.assertFalse(self.client.get(f"/api/sessions/{session['id']}").json()["answers"][other_q["id"]]["assisted"])

    def test_weak_practice_is_from_real_history_and_correct_retry_clears_it(self):
        course = self.course()
        self.assertEqual(self.client.post(f"/api/courses/{course['id']}/sessions", json={"unit_id": "unit-1", "expected_revision": 2, "exercise": "weak"}).status_code, 409)
        first = self.begin(course); self.answer_all(first, wrong=True)
        weak = self.client.get(f"/api/courses/{course['id']}/weak-items").json()
        self.assertEqual(len(weak["questions"]), 4)
        second = self.begin(course, mode="practice", exercise="weak", question_types=["mcq", "cloze"])
        self.assertEqual(len(second["questions"]), 2)
        self.answer_all(second)
        self.assertEqual({q["question"]["kind"] for q in self.client.get(f"/api/courses/{course['id']}/weak-items").json()["questions"]}, {"matching", "ordering"})

    def test_multi_unit_practice_respects_unlock_and_type_count(self):
        course = self.course()
        body = {"unit_ids": ["unit-1", "unit-2"], "expected_revision": 2, "mode": "practice"}
        self.assertEqual(self.client.post(f"/api/courses/{course['id']}/sessions", json=body).status_code, 403)
        self.answer_all(self.begin(course), wrong=True)
        self.job(self.client.post(f"/api/courses/{course['id']}/generate", json={"unit_id": "unit-2", "expected_revision": 2}))
        body.update(expected_revision=3, question_types=["mcq"], question_count=2)
        session = self.client.post(f"/api/courses/{course['id']}/sessions", json=body).json()
        self.assertEqual({q["unit_id"] for q in session["questions"]}, {"unit-1", "unit-2"})
        self.assertEqual({q["kind"] for q in session["questions"]}, {"mcq"})
        self.assertEqual(self.client.post(f"/api/courses/{course['id']}/sessions", json={**body, "question_count": 3}).status_code, 422)
        self.assertEqual(self.client.post(f"/api/courses/{course['id']}/sessions", json={**body, "difficulty": "hard"}).status_code, 422)

    def test_save_question_personal_card_once_and_edit_does_not_change_course(self):
        course = self.course(); session = self.begin(course)
        body = {"session_id": session["id"], "item_id": session["questions"][0]["id"]}
        first = self.client.post('/api/cards/from-question', json=body).json()
        second = self.client.post('/api/cards/from-question', json=body).json()
        self.assertEqual(first["id"], second["id"])
        cards = self.client.get('/api/cards', params={"course_id": course["id"]}).json()
        personal = next(c for c in cards if c["id"] == first["id"])
        memo = {"course_id": course["id"], "expected_revision": 2, "expected_version": 0, "remembered": True}
        self.client.put(f"/api/cards/{personal['id']}/memory", json=memo).raise_for_status()
        edit = {"front": "Câu của mình", "back": "Ghi nhớ riêng", "course_id": course["id"], "source_refs": personal["source_refs"], "expected_version": 1}
        self.client.put(f"/api/cards/{personal['id']}", json=edit).raise_for_status()
        self.assertEqual(self.client.put(f"/api/cards/{personal['id']}", json=edit).status_code, 409)
        changed = next(c for c in self.client.get('/api/cards', params={"course_id": course["id"]}).json() if c["id"] == personal["id"])
        self.assertIsNone(changed["memory"]["remembered"])
        self.assertEqual(self.client.get(f"/api/courses/{course['id']}/editor").json()["content"], course["content"])

    def test_generated_card_memory_survives_unrelated_question_revision(self):
        course = self.course()
        card = self.client.get('/api/cards', params={"course_id": course["id"]}).json()[0]
        self.client.put(f"/api/cards/{card['id']}/memory", json={"course_id": course["id"], "expected_revision": 2, "remembered": False}).raise_for_status()
        question = copy.deepcopy(course["content"]["units"][0]["data"]["questions"][0]); question["prompt"] = "Đề đã chỉnh"
        proposed = self.client.post(f"/api/courses/{course['id']}/proposals", json={"unit_id": "unit-1", "expected_revision": 2, "target": "question", "index": 0, "request": "Sửa đề", "replacement": question}).json()
        self.client.post(f"/api/proposals/{proposed['proposal_id']}/apply", json={"expected_revision": 2}).raise_for_status()
        cards = self.client.get('/api/cards', params={"course_id": course["id"]}).json()
        self.assertEqual(cards[0]["id"], card["id"])
        self.assertFalse(cards[0]["memory"]["remembered"])

    def test_notebook_ownership_revision_refs_soft_delete_restore(self):
        course = self.course(); refs = course["content"]["units"][0]["data"]["sections"][0]["source_refs"]
        body = {"body": "Ghi chú riêng", "course_id": course["id"], "source_refs": refs}
        note = self.client.post('/api/notebook', json=body).json()
        edit = {**body, "body": "Bản đã sửa", "expected_version": 1}
        self.client.put('/api/notebook/' + note["id"], json=edit).raise_for_status()
        self.assertEqual(self.client.put('/api/notebook/' + note["id"], json=edit).status_code, 409)
        self.assertEqual(self.client.post('/api/notebook', json={**body, "source_refs": ["fake:1:0"]}).status_code, 404)
        with TestClient(self.app, base_url="http://127.0.0.1") as outsider:
            outsider.post('/api/session')
            self.assertEqual(outsider.get('/api/notebook').json(), [])
            self.assertEqual(outsider.put('/api/notebook/' + note["id"], json=edit).status_code, 404)
            self.assertEqual(outsider.delete('/api/notebook/' + note["id"]).status_code, 404)
        self.client.delete('/api/notebook/' + note["id"]).raise_for_status()
        self.assertEqual(self.client.get('/api/notebook').json(), [])
        self.assertEqual(self.client.post(f"/api/notebook/{note['id']}/restore").json()["body"], "Bản đã sửa")

    def test_note_colour_is_owner_only_kept_through_delete_and_limited_to_the_palette(self):
        note = self.client.post('/api/notebook', json={"body": "Mẹo nhớ subnet", "color": "mint"}).json()
        self.assertEqual(note["color"], "mint")
        changed = self.client.put(f"/api/notebook/{note['id']}/color", json={"color": "pink"}).json()
        self.assertEqual((changed["color"], changed["version"], changed["body"]), ("pink", 1, "Mẹo nhớ subnet"))
        self.assertEqual(self.client.put(f"/api/notebook/{note['id']}/color", json={"color": "#ff0000"}).status_code, 422)
        self.assertIsNone(self.client.post('/api/notebook', json={"body": "Không chọn màu"}).json()["color"])
        with TestClient(self.app, base_url="http://127.0.0.1") as outsider:
            outsider.post('/api/session')
            self.assertEqual(outsider.put(f"/api/notebook/{note['id']}/color", json={"color": "sky"}).status_code, 404)
        self.client.delete('/api/notebook/' + note["id"]).raise_for_status()
        self.assertEqual(self.client.put(f"/api/notebook/{note['id']}/color", json={"color": "sky"}).status_code, 404)
        self.assertEqual(self.client.post(f"/api/notebook/{note['id']}/restore").json()["color"], "pink")

    def test_save_chat_note_uses_server_message_and_ai_label_once(self):
        course = self.course()
        self.job(self.client.post(f"/api/courses/{course['id']}/chat", json={"unit_id": "unit-1", "message": "Hint"}))
        messages = self.client.get(f"/api/courses/{course['id']}/chat").json()
        body = {"message_id": messages[-1]["id"]}
        first = self.client.post('/api/notebook/from-chat', json=body).json()
        second = self.client.post('/api/notebook/from-chat', json=body).json()
        self.assertEqual(first, second); self.assertEqual(first["label"], "ai")
        self.assertEqual(first["body"], messages[-1]["text"])
        self.assertEqual(self.client.post('/api/notebook', json={"body": "Pretend AI", "label": "ai"}).status_code, 422)

    def test_reported_question_is_not_used_in_new_attempt_but_old_attempt_is_pinned(self):
        course = self.course(); old = self.begin(course)
        q = old["questions"][0]
        self.client.post(f"/api/courses/{course['id']}/question-reports", json={"expected_revision": 2, "unit_id": "unit-1", "item_id": q["id"], "reason": "Cần đối chiếu đáp án"}).raise_for_status()
        new = self.begin(course)
        self.assertNotIn(q["id"], {x["id"] for x in new["questions"]})
        self.assertIn(q["id"], {x["id"] for x in self.client.get(f"/api/sessions/{old['id']}").json()["questions"]})

    def test_chat_receives_question_answer_context_and_rejects_foreign_context(self):
        course = self.course(); session = self.begin(course); q = session["questions"][0]
        self.client.post(f"/api/sessions/{session['id']}/answers", json={"item_id": q["id"], "answer": "option-1"}).raise_for_status()
        body = {"unit_id": "unit-1", "message": "Vì sao mình sai?", "session_id": session["id"], "item_id": q["id"]}
        self.job(self.client.post(f"/api/courses/{course['id']}/chat", json=body))
        self.assertIn('"learner_answer": "option-1"', self.provider.instructions[-1])
        self.assertIn(q["prompt"], self.provider.instructions[-1])
        calls = self.provider.calls
        self.assertEqual(self.client.post(f"/api/courses/{course['id']}/chat", json={**body, "session_id": "another-user-session"}).status_code, 404)
        self.assertEqual(self.provider.calls, calls)
