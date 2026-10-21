"""Source changes are scoped previews, not rewrites of learned material."""
import copy
import json
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from test_slice import SliceFixture, FIXTURE_SOURCE
from study_backend.models import QUESTION_DRAFTS


class SourceBindingTests(SliceFixture):
    def setUp(self):
        super().setUp()
        self.received = []
        generate = self.provider.generate

        async def capture(schema, instruction, fragments):
            self.received.append({'schema': schema.__name__, 'fragments': copy.deepcopy(fragments), 'instruction': instruction})
            return await generate(schema, instruction, fragments)
        self.provider.generate = capture

    def peer(self):
        client = TestClient(self.app, base_url='http://127.0.0.1')
        client.post('/api/session').raise_for_status()
        self.addCleanup(client.close)
        return client

    def new_source(self, name='new.txt', client=None, review=True):
        client = client or self.client
        response = client.post('/api/sources/upload', files={'file': (name, FIXTURE_SOURCE + b'\nNew source marker.', 'text/plain')})
        response.raise_for_status()
        source = response.json()
        if review:
            response = client.post('/api/sources/' + source['id'] + '/review', json={'expected_revision': 1, 'texts': [f['text'] for f in source['fragments']]})
            response.raise_for_status()
            source = response.json()
        return source

    def three_units(self):
        source = self.source()
        source = self.client.post('/api/sources/' + source['id'] + '/review', json={'expected_revision': 1, 'texts': [f['text'] for f in source['fragments']]}).json()
        plan_id = self.job(self.client.post('/api/plans', json=self.preferences(source)))['plan_id']
        plan = self.client.get('/api/plans/' + plan_id).json()
        outline = {k: v for k, v in plan['outline'].items() if k != 'version'}
        outline['units'].append({**outline['units'][1], 'title': 'Bài 3'})
        self.client.put('/api/plans/' + plan_id, json={'expected_version': 1, 'outline': outline}).raise_for_status()
        course_id = self.client.post('/api/plans/' + plan_id + '/approve', json={'expected_revision': 2}).json()['course_id']
        self.job(self.client.post('/api/courses/' + course_id + '/generate', json={'expected_revision': 1, 'unit_id': 'unit-1'}))
        return self.client.get('/api/courses/' + course_id + '/editor').json()

    def unit_edit(self, source, unit_id='unit-2'):
        return {'unit_id': unit_id, 'title': 'Bài dùng nguồn đã chọn', 'objective': 'Đối chiếu đúng bản nguồn',
                'source_id': source['id'], 'expected_extraction_revision': source['revision'],
                'source_refs': [f['id'] for f in source['fragments']]}

    def preview(self, course, units, **extra):
        response = self.client.post('/api/courses/' + course['id'] + '/future-plan-preview',
                                    json={'expected_revision': course['revision'], 'units': units, 'request': 'Đổi nguồn phần chưa tạo', **extra})
        response.raise_for_status()
        return self.client.get('/api/proposals/' + response.json()['proposal_id']).json()

    def apply(self, preview):
        response = self.client.post('/api/proposals/' + preview['id'] + '/apply', json={'expected_revision': preview['base_revision']})
        response.raise_for_status()
        return self.client.get('/api/courses/' + preview['course_id'] + '/editor').json()

    def chapter_draft(self):
        source = self.client.post('/api/sources/text', json={'name': 'approved-chapter.txt', 'text': '\n'.join([
            'IPv4 uses 32 bits.', 'A prefix separates network and host bits.',
            'Network sets host bits to zero.', 'Broadcast sets host bits to one.',
            'Apply the prefix to identify both boundaries.', 'EXCLUDED_PRIVATE_CHAPTER'])}).json()
        source = self.client.post('/api/sources/' + source['id'] + '/review', json={
            'expected_revision': 1, 'texts': [f['text'] for f in source['fragments']]}).json()
        refs = [f['id'] for f in source['fragments'][:-1]]
        prefs = {**self.preferences(source), 'fragment_ids': refs,
                 'excluded_fragment_ids': [source['fragments'][-1]['id']], 'unlock_policy': 'open',
                 'question_types': ['mcq'], 'question_count': 1}
        plan = self.client.post('/api/plans/from-source-sections', json=prefs).json()
        outline = {'title': 'Approved chapter', 'units': [
            {'title': 'Principles', 'objective': 'Understand prefix boundaries.', 'source_refs': refs[:-1]},
            {'title': 'Application', 'objective': 'Apply the prefix.', 'source_refs': refs[-1:]}]}
        self.client.put('/api/plans/' + plan['id'], json={'expected_version': 1, 'outline': outline}).raise_for_status()
        cid = self.client.post('/api/plans/' + plan['id'] + '/approve', json={'expected_revision': 2}).json()['course_id']
        return self.client.get('/api/courses/' + cid + '/editor').json(), source, refs

    def test_preference_only_edit_preserves_entire_chapter_and_its_exclusions(self):
        course, source, refs = self.chapter_draft()
        before = self.client.get('/api/courses/' + course['id'] + '/source-bindings').json()['units']
        calls = self.provider.calls; wallet = self.client.get('/api/wallet').json()
        edit = {'unit_id': 'unit-2', 'title': 'Explain the application', 'objective': 'Apply the approved principles.',
                'source_refs': refs[-1:]}
        preview = self.preview(course, [edit], preferences={'language': 'en'})
        after = preview['source_bindings']['after']
        self.assertEqual(after[0], preview['source_bindings']['before'][0])
        self.assertEqual(after[0]['plan_id'], before[0]['plan_id'])
        self.assertEqual(after[1]['focus_source_refs'], refs[-1:])
        self.assertEqual(after[1]['preferences']['fragment_ids'], refs)
        self.assertEqual(after[1]['preferences']['excluded_fragment_ids'], [source['fragments'][-1]['id']])
        self.assertEqual(after[1]['chapter_scope'], {'selected_fragments': 5, 'source_fragments': 6,
                         'full_source': False, 'method': 'preserved_approved_chapter', 'chapter_boundary_inferred': False})
        current = self.apply(preview)
        self.assertEqual(self.provider.calls, calls); self.assertEqual(self.client.get('/api/wallet').json(), wallet)
        start = len(self.received)
        self.job(self.client.post('/api/courses/' + course['id'] + '/generate', json={
            'expected_revision': current['revision'], 'unit_id': 'unit-2'}))
        self.assertEqual({f['id'] for call in self.received[start:] for f in call['fragments']}, set(refs))
        self.assertNotIn('EXCLUDED_PRIVATE_CHAPTER', json.dumps(self.received[start:], ensure_ascii=False))

    def test_partial_new_source_requires_explicit_chapter_before_writes_coin_or_ai(self):
        course, _, _ = self.chapter_draft(); source = self.new_source()
        focus = source['fragments'][-1]['id']; edit = {**self.unit_edit(source), 'source_refs': [focus]}
        body = {'expected_revision': 1, 'request': 'Change the future source', 'units': [edit]}
        path = '/api/courses/' + course['id'] + '/future-plan-preview'
        with self.app.state.database.connection() as db:
            before = [db.execute('SELECT count(*) FROM ' + table).fetchone()[0] for table in ['plans', 'revision_proposals']]
        calls = self.provider.calls; wallet = self.client.get('/api/wallet').json()
        response = self.client.post(path, json=body)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['detail']['code'], 'CHAPTER_SCOPE_REQUIRED')
        with self.app.state.database.connection() as db:
            self.assertEqual(before, [db.execute('SELECT count(*) FROM ' + table).fetchone()[0] for table in ['plans', 'revision_proposals']])
        self.assertEqual(self.provider.calls, calls); self.assertEqual(self.client.get('/api/wallet').json(), wallet)
        self.assertEqual(self.client.get('/api/courses/' + course['id'] + '/editor').json(), course)

    def test_explicit_new_chapter_is_previewed_pinned_and_does_not_read_other_sections(self):
        course, _, _ = self.chapter_draft(); source = self.new_source()
        chapter = [f['id'] for f in source['fragments'][-2:]]
        edit = {**self.unit_edit(source), 'source_refs': chapter[-1:], 'chapter_fragment_ids': chapter}
        preview = self.preview(course, [edit]); binding = preview['source_bindings']['after'][1]
        self.assertEqual(binding['preferences']['fragment_ids'], chapter)
        self.assertEqual(binding['chapter_scope']['method'], 'explicit_chapter_selection')
        self.assertFalse(binding['chapter_scope']['full_source'])
        self.assertEqual(binding['chapter_scope']['selected_fragments'], 2)
        current = self.apply(preview); start = len(self.received)
        self.job(self.client.post('/api/courses/' + course['id'] + '/generate', json={
            'expected_revision': current['revision'], 'unit_id': 'unit-2'}))
        self.assertEqual({f['id'] for call in self.received[start:] for f in call['fragments']}, set(chapter))

    def test_explicit_chapter_rejects_foreign_duplicate_or_missing_focus_without_side_effects(self):
        course, _, refs = self.chapter_draft(); source = self.new_source()
        focus = source['fragments'][-1]['id']; valid = {**self.unit_edit(source), 'source_refs': [focus]}
        invalid = [[focus, refs[0]], [focus, focus], [source['fragments'][0]['id']]]
        wallet = self.client.get('/api/wallet').json(); calls = self.provider.calls
        for chapter in invalid:
            response = self.client.post('/api/courses/' + course['id'] + '/future-plan-preview', json={
                'expected_revision': 1, 'request': 'Change scope', 'units': [{**valid, 'chapter_fragment_ids': chapter}]})
            self.assertEqual(response.status_code, 422)
        self.assertEqual(self.provider.calls, calls); self.assertEqual(self.client.get('/api/wallet').json(), wallet)
        self.assertEqual(self.client.get('/api/courses/' + course['id'] + '/editor').json(), course)

    def test_new_material_only_changes_selected_draft_and_each_generation_uses_its_sources(self):
        course = self.three_units(); path = '/api/courses/' + course['id']
        original = copy.deepcopy(course['content']['units'][0])
        session = self.client.post(path + '/sessions', json={'expected_revision': 2, 'unit_id': 'unit-1'}).json()
        self.client.post('/api/sessions/' + session['id'] + '/answers', json={'item_id': session['questions'][0]['id'], 'answer': 'option-1'}).raise_for_status()
        old_attempt = self.client.get('/api/sessions/' + session['id']).json()
        source = self.new_source()
        calls = self.provider.calls
        preview = self.preview(course, [self.unit_edit(source)], preferences={'language': 'en', 'unlock_policy': 'open', 'question_types': ['mcq'], 'question_count': 1, 'card_count': 1})
        self.assertEqual(self.client.get(path).json()['revision'], 2)
        self.assertEqual(self.provider.calls, calls)
        before = {v['unit_id']: v for v in preview['source_bindings']['before']}
        after = {v['unit_id']: v for v in preview['source_bindings']['after']}
        self.assertEqual(after['unit-1'], before['unit-1'])
        self.assertEqual(after['unit-3'], before['unit-3'])
        self.assertEqual(after['unit-2']['source_id'], source['id'])
        course = self.apply(preview)
        self.assertEqual(self.provider.calls, calls)
        self.assertEqual(course['content']['units'][0]['data'], original['data'])
        self.assertEqual(self.client.get('/api/sessions/' + session['id']).json(), old_attempt)
        start = len(self.received)
        self.job(self.client.post(path + '/generate', json={'expected_revision': 3, 'unit_id': 'unit-2'}))
        self.assertEqual({f['id'] for call in self.received[start:] for f in call['fragments']}, {f['id'] for f in source['fragments']})
        self.assertTrue(all('"language": "en"' in call['instruction'] for call in self.received[start:]))
        start = len(self.received)
        self.job(self.client.post(path + '/generate', json={'expected_revision': 4, 'unit_id': 'unit-3'}))
        self.assertEqual({f['id'] for call in self.received[start:] for f in call['fragments']}, set(original['source_refs']))
        self.assertTrue(all('"language": "vi"' in call['instruction'] for call in self.received[start:]))
        units = self.client.get(path + '/source-bindings').json()['units']
        self.assertEqual([u['source_id'] for u in units], [before['unit-1']['source_id'], source['id'], before['unit-1']['source_id']])

    def test_new_extraction_keeps_generated_lesson_old_text_and_version(self):
        course = self.course(); path = '/api/courses/' + course['id']
        old = self.client.get(path + '/source-bindings').json()['units'][0]
        source = self.client.get('/api/sources/' + old['source_id']).json()
        texts = [f['text'] + ' Corrected extraction marker.' for f in source['fragments']]
        response = self.client.post('/api/sources/' + source['id'] + '/review', json={'expected_revision': source['revision'], 'texts': texts})
        response.raise_for_status(); source = response.json()
        preview = self.preview(course, [self.unit_edit(source)], preferences={'unlock_policy': 'open'})
        course = self.apply(preview)
        bindings = self.client.get(path + '/source-bindings').json()['units']
        self.assertEqual([u['extraction_revision'] for u in bindings], [2, 3])
        old_fragments = self.client.get(path + '/source-fragments?unit_id=unit-1').json()
        self.assertFalse(any('Corrected extraction marker' in f['text'] for f in old_fragments))
        new_fragments = self.client.get(path + '/source-fragments?unit_id=unit-2').json()
        self.assertTrue(all('Corrected extraction marker' in f['text'] for f in new_fragments))
        self.assertEqual(self.client.get('/api/sources/' + source['id'] + '/original').content, FIXTURE_SOURCE)

    def test_source_must_be_owned_reviewed_exact_and_complete(self):
        course = self.course(); path = '/api/courses/' + course['id'] + '/future-plan-preview'
        source = self.new_source(review=False)
        body = {'expected_revision': 2, 'request': 'Đổi nguồn', 'units': [self.unit_edit(source)]}
        self.assertEqual(self.client.post(path, json=body).status_code, 409)
        foreign = self.new_source(client=self.peer())
        body['units'] = [self.unit_edit(foreign)]
        self.assertEqual(self.client.post(path, json=body).status_code, 404)
        source = self.new_source()
        valid = self.unit_edit(source)
        for field in ('source_id', 'expected_extraction_revision'):
            unit = valid.copy(); unit.pop(field); body['units'] = [unit]
            self.assertEqual(self.client.post(path, json=body).status_code, 422)
        body['units'] = [{**valid, 'expected_extraction_revision': 1}]
        self.assertEqual(self.client.post(path, json=body).status_code, 409)
        body['units'] = [{**valid, 'source_refs': course['content']['units'][1]['source_refs']}]
        self.assertEqual(self.client.post(path, json=body).status_code, 422)
        body['units'] = [{**valid, 'source_refs': [valid['source_refs'][0]] * 2}]
        self.assertEqual(self.client.post(path, json=body).status_code, 422)
        self.assertEqual(self.client.get('/api/courses/' + course['id']).json()['revision'], 2)

    def test_source_change_after_preview_rejects_apply_without_approving_any_plan(self):
        course = self.three_units(); first = self.new_source('first.txt'); second = self.new_source('second.txt')
        preview = self.preview(course, [self.unit_edit(first), self.unit_edit(second, 'unit-3')])
        new_plans = [v['plan_id'] for v in preview['source_bindings']['after'][1:]]
        self.client.post('/api/sources/' + second['id'] + '/review', json={'expected_revision': 2, 'texts': [f['text'] + ' New edit.' for f in second['fragments']]}).raise_for_status()
        self.assertEqual(self.client.post('/api/proposals/' + preview['id'] + '/apply', json={'expected_revision': 2}).status_code, 409)
        self.assertEqual(self.client.get('/api/courses/' + course['id']).json()['revision'], 2)
        self.assertTrue(all(self.client.get('/api/plans/' + p).json()['status'] == 'proposal_preview' for p in new_plans))
        self.client.post('/api/proposals/' + preview['id'] + '/discard').raise_for_status()
        self.assertTrue(all(self.client.get('/api/plans/' + p).json()['status'] == 'discarded' for p in new_plans))

    def test_multiple_source_plans_apply_together_and_later_edits_inherit_unit_binding(self):
        course = self.three_units(); first = self.new_source('first.txt'); second = self.new_source('second.txt')
        preview = self.preview(course, [self.unit_edit(first), self.unit_edit(second, 'unit-3')], preferences={'language': 'en'})
        course = self.apply(preview)
        before = self.client.get('/api/courses/' + course['id'] + '/source-bindings').json()['units']
        self.assertEqual([u['source_id'] for u in before[1:]], [first['id'], second['id']])
        self.assertTrue(all(self.client.get('/api/plans/' + u['plan_id']).json()['status'] == 'approved' for u in before))
        edit = {k: v for k, v in self.unit_edit(second, 'unit-3').items() if k not in {'source_id', 'expected_extraction_revision'}}
        preview = self.preview(course, [edit], preferences={'language': 'vi'})
        course = self.apply(preview)
        after = self.client.get('/api/courses/' + course['id'] + '/source-bindings').json()['units']
        self.assertEqual(after[1], before[1])
        self.assertEqual(after[2]['source_id'], second['id'])
        self.assertEqual(after[2]['preferences']['language'], 'vi')

    def test_cross_source_unit_revert_keeps_old_attempt_help_and_saved_card_context(self):
        course = self.course(); path = '/api/courses/' + course['id']; source = self.new_source()
        course = self.apply(self.preview(course, [self.unit_edit(source)], preferences={'unlock_policy': 'open'}))
        self.job(self.client.post(path + '/generate', json={'expected_revision': 3, 'unit_id': 'unit-2'}))
        session = self.client.post(path + '/sessions', json={'expected_revision': 4, 'unit_id': 'unit-2'}).json()
        item = session['questions'][0]
        card = self.client.post('/api/cards/from-question', json={'session_id': session['id'], 'item_id': item['id']}).json()
        response = self.client.post(path + '/revert-preview', json={'expected_revision': 4, 'target_revision': 2, 'unit_id': 'unit-2'})
        response.raise_for_status()
        preview = self.client.get('/api/proposals/' + response.json()['proposal_id']).json()
        course = self.apply(preview)
        self.assertIsNone(course['content']['units'][1]['data'])
        thread = self.client.post('/api/sessions/' + session['id'] + '/items/' + item['id'] + '/help')
        thread.raise_for_status()
        self.assertEqual({f['id'] for f in self.client.get('/api/help/threads/' + thread.json()['thread_id']).json()['source_excerpts']}, set(item['source_refs']))
        for context in ({'session_id': session['id'], 'item_id': item['id']}, {'card_id': card['id']}):
            start = len(self.received)
            self.job(self.client.post(path + '/chat', json={'unit_id': 'unit-2', 'message': 'Hỏi bản cũ', **context}))
            self.assertEqual({f['id'] for call in self.received[start:] for f in call['fragments']}, set(item['source_refs']))
            self.assertIn('"course_revision": 4', self.received[-1]['instruction'])
        self.assertEqual(self.client.get('/api/sessions/' + session['id']).json()['revision'], 4)

    def test_sharing_new_source_does_not_expand_original_file_grants(self):
        course = self.course(); path = '/api/courses/' + course['id']; peer = self.peer()
        def publish(course, original=True):
            response = self.client.post(path + '/publication-preview', json={'expected_revision': course['revision'], 'visibility': 'public', 'share_original': original})
            response.raise_for_status()
            self.client.post('/api/publications/' + response.json()['publication_id'] + '/apply', json={'expected_revision': course['revision']}).raise_for_status()
            return response.json()['preview']
        publish(course)
        peer.post(path + '/enroll').raise_for_status()
        source = self.new_source()
        course = self.apply(self.preview(course, [self.unit_edit(source)], preferences={'unlock_policy': 'open'}))
        self.assertEqual(peer.get('/api/sources/' + source['id'] + '/original').status_code, 404)
        self.assertEqual(peer.get(path + '/source-bindings').status_code, 404)
        self.assertEqual(peer.post(path + '/future-plan-preview', json={'expected_revision': 3, 'units': [self.unit_edit(source)], 'request': 'Sửa chung'}).status_code, 404)
        self.assertFalse(any(f['id'] in {f['id'] for f in source['fragments']} for f in peer.get(path + '/source-fragments').json()))
        self.job(self.client.post(path + '/generate', json={'expected_revision': 3, 'unit_id': 'unit-2'}))
        view = peer.get(path).json()
        self.assertTrue(all('source_plan_id' not in u for u in view['content']['units']))
        self.assertEqual({f['id'] for f in peer.get(path + '/source-fragments?unit_id=unit-2').json()}, {f['id'] for f in source['fragments']})
        self.assertEqual(peer.get('/api/sources/' + source['id'] + '/original').status_code, 404)
        course = self.client.get(path + '/editor').json()
        names = publish(course)['originals']
        self.assertIn('notes.txt', names); self.assertIn('new.txt', names)
        self.assertEqual(peer.get('/api/sources/' + source['id'] + '/original').status_code, 200)
        self.assertEqual(peer.get('/api/sources/' + source['id']).status_code, 404)

    def test_two_preview_applies_race_only_one_revision_and_no_partial_approval(self):
        course = self.three_units(); source = self.new_source()
        previews = [self.preview(course, [self.unit_edit(source), self.unit_edit(source, 'unit-3')]) for _ in range(2)]
        def apply(p):
            return self.client.post('/api/proposals/' + p['id'] + '/apply', json={'expected_revision': 2}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(apply, previews))
        self.assertEqual(sorted(statuses), [200, 409])
        self.assertEqual(self.client.get('/api/courses/' + course['id']).json()['revision'], 3)
        for status, preview in zip(statuses, previews):
            expected = 'approved' if status == 200 else 'proposal_preview'
            for unit in preview['source_bindings']['after'][1:]:
                self.assertEqual(self.client.get('/api/plans/' + unit['plan_id']).json()['status'], expected)

    def test_partial_retry_from_old_source_and_apply_during_exam_are_rejected(self):
        course = self.course(); path = '/api/courses/' + course['id']; source = self.new_source()
        course = self.apply(self.preview(course, [self.unit_edit(source)], preferences={'unlock_policy': 'open'}))
        generate = self.provider.generate
        async def fail_questions(schema, instruction, fragments):
            if schema in QUESTION_DRAFTS.values():
                raise ValueError('Test failure after saved reading')
            return await generate(schema, instruction, fragments)
        self.provider.generate = fail_questions
        response = self.client.post(path + '/generate', json={'expected_revision': 3, 'unit_id': 'unit-2'})
        response.raise_for_status(); failed = self.client.get('/api/jobs/' + response.json()['job_id']).json()
        self.assertEqual(failed['status'], 'failed'); self.assertTrue(failed['partial']['reading'])
        self.provider.generate = generate
        new_source = self.new_source('third.txt')
        preview = self.preview(course, [self.unit_edit(new_source)])
        exam = self.client.post(path + '/sessions', json={'expected_revision': 3, 'unit_id': 'unit-1', 'exercise': 'test'}).json()
        self.assertEqual(self.client.post('/api/proposals/' + preview['id'] + '/apply', json={'expected_revision': 3}).status_code, 403)
        self.client.post('/api/sessions/' + exam['id'] + '/cancel').raise_for_status()
        self.apply(preview)
        calls = self.provider.calls
        self.assertEqual(self.client.post(path + '/generate', json={'expected_revision': 4, 'unit_id': 'unit-2', 'resume_job_id': failed['id']}).status_code, 409)
        self.assertEqual(self.provider.calls, calls)

    def test_coin_quote_uses_each_units_own_question_count(self):
        course = self.three_units(); path = '/api/courses/' + course['id']; source = self.new_source()
        self.apply(self.preview(course, [self.unit_edit(source)], preferences={'unlock_policy': 'open', 'question_types': ['mcq'], 'question_count': 1}))
        self.app.state.economy.enabled = True
        self.app.state.economy.policy['initial_quota']['lesson'] = 0
        for unit_id, amount in [('unit-2', 2), ('unit-3', 6)]:
            response = self.client.post(path + '/generate', json={'expected_revision': 3, 'unit_id': unit_id})
            self.assertEqual(response.status_code, 402)
            self.assertEqual(response.json()['detail']['amount'], amount)

    def test_learner_can_save_owned_old_question_after_unit_source_is_reverted(self):
        course = self.course(); path = '/api/courses/' + course['id']; source = self.new_source()
        self.apply(self.preview(course, [self.unit_edit(source)], preferences={'unlock_policy': 'open'}))
        self.job(self.client.post(path + '/generate', json={'expected_revision': 3, 'unit_id': 'unit-2'}))
        publication = self.client.post(path + '/publication-preview', json={'expected_revision': 4, 'visibility': 'public'}).json()
        self.client.post('/api/publications/' + publication['publication_id'] + '/apply', json={'expected_revision': 4}).raise_for_status()
        peer = self.peer(); peer.post(path + '/enroll').raise_for_status()
        session = peer.post(path + '/sessions', json={'expected_revision': 4, 'unit_id': 'unit-2'}).json()
        response = self.client.post(path + '/revert-preview', json={'expected_revision': 4, 'target_revision': 2, 'unit_id': 'unit-2'})
        response.raise_for_status()
        self.apply(self.client.get('/api/proposals/' + response.json()['proposal_id']).json())
        item = session['questions'][0]
        response = peer.post('/api/cards/from-question', json={'session_id': session['id'], 'item_id': item['id']})
        response.raise_for_status()
        cards = peer.get('/api/cards').json()
        card = next(c for c in cards if c['id'] == response.json()['id'])
        self.assertEqual(card['source_refs'], item['source_refs'])
        self.assertEqual(card['origin']['course_revision'], 4)
        self.assertEqual(peer.get('/api/sources/' + source['id'] + '/original').status_code, 404)
        self.assertEqual(self.client.post('/api/cards/from-question', json={'session_id': session['id'], 'item_id': item['id']}).status_code, 404)
