"""Question-target distribution and pinned HTTP workflow, not semantic scoring."""
import copy
import asyncio
import json
import unittest
from pathlib import Path
import httpx

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from study_backend.app import create_app
from study_backend.chapter_context import ChapterBrief
from study_backend.gemini import ProviderError
from study_backend.models import LessonReading, Question, QUESTION_DRAFTS
from study_backend.question_generation import question_prompt
from study_backend import question_focus as focus
from test_slice import SliceFixture


class FocusPlanTests(unittest.TestCase):
    def inputs(self):
        fragments = [{'id': 'net', 'text': 'IPv4 prefix: network bits and host bits. Network address: host bits zero. Broadcast address: host bits one.'}]
        unit = {'id': 'u', 'title': 'IPv4 network address', 'objective': 'Understand network bits, host bits and broadcast address'}
        prefs = {'question_types': ['mcq', 'cloze', 'matching', 'ordering', 'short_answer'], 'question_count': 8}
        reading = {'sections': [{'title': 'IPv4', 'source_refs': ['net']}]}
        brief = {'question_targets': ['Calculate network bits and host bits', 'Distinguish network address and broadcast address',
                                      'Compare network host bits with broadcast host bits', 'Operant conditioning and punishment']}
        return ['context', {'sha256': 'evidence', 'focus_source_refs': ['net']}, unit, prefs, reading, brief, fragments]

    def test_repeated_kinds_use_different_chapter_targets_and_exclude_unrelated_target(self):
        args = self.inputs(); before = copy.deepcopy(args)
        plan = focus.prepare(*args)
        topics = [v['topic'] for v in plan['assignments'].values()]
        self.assertNotIn('Operant conditioning and punishment', topics)
        self.assertEqual(len(plan['assignments']), 8)
        for kind in ('mcq', 'cloze', 'matching'):
            same = [v['topic'] for v in plan['assignments'].values() if v['kind'] == kind]
            self.assertEqual(len(set(same)), len(same))
        self.assertEqual(args, before)
        self.assertEqual(focus.prepare(*args, previous=plan), plan)
        self.assertEqual(plan['ai_calls'], 0)

    def test_saved_targets_fail_closed_when_reading_scope_or_analysis_changes(self):
        args = self.inputs(); plan = focus.prepare(*args)
        for index, value in [(0, 'other-context'), (1, {'sha256': 'new', 'focus_source_refs': ['net']}),
                             (4, {'sections': [{'title': 'Changed', 'source_refs': ['net']}]}),
                             (5, {'question_targets': ['Other analysis']})]:
            changed = copy.deepcopy(args); changed[index] = value
            with self.assertRaises(HTTPException): focus.prepare(*changed, previous=plan)

    def test_brief_item_bounds_are_in_schema_and_preserve_existing_accepted_contract(self):
        base = {'summary': 'Short chapter', 'key_ideas': [], 'connections': [], 'misconceptions': [],
                'question_targets': [], 'source_refs': ['ref']}
        for field in ('key_ideas', 'connections', 'misconceptions', 'question_targets'):
            item_schema = ChapterBrief.model_json_schema()['properties'][field]['items']
            self.assertEqual((item_schema['minLength'], item_schema['maxLength']), (1, 300))
            ChapterBrief.model_validate({**base, field: ['x' * 300]})
            for value in ('', ' ', 'x' * 301):
                with self.assertRaises(ValidationError): ChapterBrief.model_validate({**base, field: [value]})

    def test_cross_kind_prompts_are_labelled_and_same_kind_is_the_only_diversity_restriction(self):
        prior = [{'kind': 'matching', 'prompt': 'Match the steps'}, {'kind': 'mcq', 'prompt': 'Choose a prefix'}]
        prompt = question_prompt('Source-bound instruction', 'ordering', 'Order a real procedure', prior)
        self.assertNotIn('Match the steps', prompt)
        self.assertNotIn('Choose a prefix', prompt)
        self.assertNotIn('Đã có câu CÙNG DẠNG:', prompt)
        same = question_prompt('Source-bound instruction', 'mcq', 'Choose a prefix', prior)
        self.assertIn('"kind": "mcq"', same)
        self.assertNotIn('Match the steps', same)
        self.assertIn('Đã có câu CÙNG DẠNG: ["Choose a prefix"]', same)

    def test_long_previous_questions_are_bounded_labelled_excerpts_not_silently_full_sources(self):
        prior = [{'kind': 'mcq', 'prompt': 'q' * 1900 + 'TAIL'}]
        prompt = question_prompt('SOURCE_TAIL_INTACT', 'mcq', 'Objective', prior)
        self.assertIn('"excerpt": true', prompt)
        self.assertNotIn('TAIL"', prompt)
        self.assertIn('SOURCE_TAIL_INTACT', prompt)
        self.assertLess(len(prompt), 5000)

    def test_ordering_uses_a_proved_procedure_not_an_incompatible_conceptual_target(self):
        args = self.inputs()
        args[5]['question_targets'] = ['Distinguish function value from antiderivative value']
        args[6][0]['text'] += '\nProcedure: (1) read the prefix; (2) calculate host bits.'
        plan = focus.prepare(*args)
        item = plan['assignments']['ordering']
        self.assertEqual(item['basis'], 'explicit_source_sequence')
        self.assertEqual(item['sequence_source_refs'], ['net'])
        self.assertNotIn('antiderivative', focus.instruction(plan, 'ordering'))
        # No true procedure means a backend gate, not invented source order.
        args[6][0]['text'] = 'First concept and second concept are distinct.'
        blocked = focus.prepare(*args)['assignments']['ordering']
        self.assertEqual(blocked['basis'], 'backend_source_gate')

    def test_old_focus_plan_is_reused_without_relabelling_its_version_or_retargeting(self):
        args = self.inputs(); old = focus.prepare(*args)
        old['version'] = focus.LEGACY_FOCUS_VERSION
        old['assignments']['ordering'] = {'kind': 'ordering', 'topic': 'Old conceptual hint', 'basis': 'chapter_question_target', 'index': 0}
        old['sha256'] = focus.digest({k:v for k,v in old.items() if k != 'sha256'})
        before = copy.deepcopy(old)
        self.assertEqual(focus.prepare(*args, previous=old), before)
        self.assertEqual(old, before)


class FocusWorkflowTests(SliceFixture):
    def install(self, fail=None, decline=None):
        original = self.provider.generate
        self.events = []
        targets = ['Đọc prefix rồi tính số bit host', 'Phân biệt địa chỉ network và broadcast', 'Tính số địa chỉ từ prefix IPv4']
        async def generate(schema, instruction, fragments):
            event = {'schema': schema, 'instruction': instruction}
            self.events.append(event)
            if schema in QUESTION_DRAFTS.values():
                with self.app.state.database.connection() as db:
                    row = db.execute("SELECT id,partial_json FROM jobs WHERE status='running' ORDER BY created_at DESC LIMIT 1").fetchone()
                    event['partial'] = json.loads(row['partial_json']); event['job_id'] = row['id']
            value = await original(schema, instruction, fragments)
            if schema is ChapterBrief: value['question_targets'] = targets
            if schema is fail: raise ProviderError('CONNECTION_FAILED', 'Fixture disconnect', True)
            if schema is decline: return {'question': None, 'reason': 'Test adapter decline'}
            if schema in QUESTION_DRAFTS.values():
                value['question']['prompt'] += ' · ' + str(len(self.events))
            return value
        self.provider.generate = generate

    def draft(self, kinds=None, count=3):
        source = self.client.post('/api/sources/text', json={'name': 'network.txt', 'text':
            'IPv4 có 32 bit. Prefix xác định số bit network, số bit host là 32 trừ prefix.\n'
            'Địa chỉ network có tất cả bit host bằng 0; broadcast có tất cả bit host bằng 1.\n'
            'Quy trình: (1) read the prefix; (2) calculate host bits.\n'
            'Số địa chỉ trong subnet là 2 mũ số bit host.'}).json()
        source = self.client.post(f"/api/sources/{source['id']}/review", json={'expected_revision': 1,
            'texts': [f['text'] for f in source['fragments']]}).json()
        plan = self.job(self.client.post('/api/plans', json={**self.preferences(source),
            'question_types': kinds or ['mcq', 'cloze', 'matching'], 'question_count': count}))
        return self.client.post('/api/plans/' + plan['plan_id'] + '/approve', json={'expected_revision': 1}).json()['course_id']

    def generate(self, cid, **extra):
        return self.client.post(f'/api/courses/{cid}/generate', json={'expected_revision': 1, 'unit_id': 'unit-1', **extra})

    def editor(self, cid):
        return self.client.get(f'/api/courses/{cid}/editor').json()

    def test_targets_are_pinned_before_inference_and_no_extra_planning_call_is_made(self):
        self.install(); cid = self.draft(['mcq', 'cloze', 'matching'], 6)
        self.job(self.generate(cid))
        unit = self.editor(cid)['content']['units'][0]
        generation = unit['generation']; plan = generation['question_focus_plan']
        questions = [e for e in self.events if e['schema'] in QUESTION_DRAFTS.values()]
        self.assertEqual(len(questions), 6)
        self.assertEqual(sum(e['schema'] is ChapterBrief for e in self.events), 1)
        self.assertEqual(sum(e['schema'] is LessonReading for e in self.events), 1)
        self.assertEqual(set(generation['stage_focus']), set(plan['assignments']))
        for event in questions:
            partial = event['partial']
            self.assertEqual(partial['question_focus_plan'], plan)
            self.assertTrue(any(v['job_id'] == event['job_id'] for v in partial['stage_focus'].values()))
        for kind in ('mcq', 'cloze', 'matching'):
            selected = [v['topic'] for v in plan['assignments'].values() if v['kind'] == kind]
            self.assertEqual(len(set(selected)), 2)
        session = self.client.post(f'/api/courses/{cid}/sessions', json={
            'expected_revision': 2, 'unit_id': 'unit-1', 'exercise': 'test'}).json()
        public = self.client.get(f'/api/courses/{cid}').json()
        public_generation = public['content']['units'][0]['generation']
        self.assertNotIn('question_focus_plan', public_generation)
        self.assertNotIn('stage_focus', public_generation)
        self.assertIn('question_coverage', public_generation)
        self.assertEqual(self.client.get(f'/api/courses/{cid}/editor').status_code, 403)
        self.client.post('/api/sessions/' + session['id'] + '/cancel').raise_for_status()
        self.assertEqual(self.editor(cid)['content']['units'][0]['generation']['question_focus_plan'], plan)

    def test_restart_resume_keeps_targets_reading_saved_questions_and_old_job(self):
        self.install(fail=QUESTION_DRAFTS['matching']); cid = self.draft()
        jid = self.generate(cid).json()['job_id']; failed = self.client.get('/api/jobs/' + jid).json()
        self.assertEqual(failed['status'], 'failed')
        partial = failed['partial']; before = copy.deepcopy(self.editor(cid))
        self.client.close()
        self.app = create_app(self.app.state.database.path, Path(self.temp.name) / 'sources', self.provider, economy_enabled=False)
        self.client = TestClient(self.app, base_url='http://127.0.0.1', cookies=self.client.cookies)
        # The underlying test adapter is retained; replace the deliberate fault.
        from test_slice import TestProvider
        self.provider.generate = TestProvider.generate.__get__(self.provider)
        calls = self.provider.calls
        self.job(self.generate(cid, resume_job_id=jid))
        self.assertEqual(self.provider.calls - calls, 1)
        unit = self.editor(cid)['content']['units'][0]
        self.assertEqual(unit['generation']['question_focus_plan'], partial['question_focus_plan'])
        self.assertEqual(unit['data']['sections'], partial['reading']['sections'])
        self.assertEqual(unit['data']['questions'][:2], [Question.model_validate(v['question']).model_dump() for v in partial['questions'].values()])
        self.assertEqual(unit['generation']['stage_focus']['mcq'], partial['stage_focus']['mcq'])
        self.assertNotEqual(unit['generation']['stage_focus']['matching']['job_id'], jid)
        self.assertEqual(self.client.get('/api/jobs/' + jid).json(), failed)
        self.assertEqual(before['revision'], 1)

    def test_tampered_focus_checkpoint_is_rejected_before_new_job_coin_or_inference(self):
        self.install(fail=QUESTION_DRAFTS['matching']); cid = self.draft()
        jid = self.generate(cid).json()['job_id']; before = self.editor(cid)
        with self.app.state.database.connection(write=True) as db:
            partial = json.loads(db.execute('SELECT partial_json FROM jobs WHERE id=?', (jid,)).fetchone()[0])
            partial['question_focus_plan']['assignments']['matching']['topic'] = 'Unapproved topic'
            db.execute('UPDATE jobs SET partial_json=? WHERE id=?', (json.dumps(partial), jid))
            count = db.execute('SELECT count(*) FROM jobs').fetchone()[0]
        calls = self.provider.calls; wallet = self.client.get('/api/wallet').json()
        self.assertEqual(self.generate(cid, resume_job_id=jid).status_code, 409)
        self.assertEqual(self.provider.calls, calls)
        self.assertEqual(self.client.get('/api/wallet').json(), wallet)
        self.assertEqual(self.editor(cid), before)
        with self.app.state.database.connection() as db: self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0], count)

    def test_legacy_saved_questions_are_not_relabelled_as_having_used_new_targets(self):
        self.install(fail=QUESTION_DRAFTS['matching']); cid = self.draft()
        jid = self.generate(cid).json()['job_id']
        with self.app.state.database.connection(write=True) as db:
            partial = json.loads(db.execute('SELECT partial_json FROM jobs WHERE id=?', (jid,)).fetchone()[0])
            for key in ('question_focus_plan', 'stage_focus'): partial.pop(key)
            db.execute('UPDATE jobs SET partial_json=? WHERE id=?', (json.dumps(partial), jid))
        from test_slice import TestProvider
        self.provider.generate = TestProvider.generate.__get__(self.provider)
        self.job(self.generate(cid, resume_job_id=jid))
        unit = self.editor(cid)['content']['units'][0]
        self.assertEqual(set(unit['generation']['stage_focus']), {'matching'})
        self.assertEqual(unit['data']['questions'][:2], [Question.model_validate(v['question']).model_dump() for v in partial['questions'].values()])

    def test_completion_only_adds_focus_provenance_in_preview_history_and_preserves_old_version(self):
        self.install(decline=QUESTION_DRAFTS['matching']); cid = self.draft()
        self.job(self.generate(cid)); before = self.editor(cid)
        original_focus = before['content']['units'][0]['generation']['question_focus_plan']
        from test_slice import TestProvider
        self.provider.generate = TestProvider.generate.__get__(self.provider)
        result = self.job(self.client.post(f'/api/courses/{cid}/question-completion', json={
            'expected_revision': 2, 'unit_id': 'unit-1', 'stages': ['matching']}))
        self.assertEqual(self.editor(cid), before)
        self.client.get('/api/proposals/' + result['proposal_id']).raise_for_status()
        self.client.post('/api/proposals/' + result['proposal_id'] + '/apply', json={'expected_revision': 2}).raise_for_status()
        current = self.editor(cid)['content']['units'][0]
        self.assertEqual(current['data']['questions'][:-1], before['content']['units'][0]['data']['questions'])
        self.assertEqual(current['generation']['question_focus_plan'], original_focus)
        history = current['generation']['question_completion_history'][-1]
        self.assertEqual(set(history['stage_focus']), {'matching'})
        self.assertEqual(history['question_focus_plan']['context_id'], original_focus['context_id'])
        public = self.client.get(f'/api/courses/{cid}').json()['content']['units'][0]['generation']
        self.assertNotIn('question_focus_plan', public)
        self.assertNotIn('question_focus_plan', public['question_completion_history'][-1])
        self.assertNotIn('stage_focus', public['question_completion_history'][-1])

    def test_cancel_during_a_question_keeps_pinned_targets_and_never_commits_reading(self):
        self.install(); cid = self.draft()
        original = self.provider.generate
        async def scenario():
            entered = asyncio.Event()
            async def block(schema, *args):
                if schema is QUESTION_DRAFTS['cloze']:
                    entered.set(); await asyncio.Future()
                return await original(schema, *args)
            self.provider.generate = block
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://127.0.0.1', cookies=self.client.cookies) as client:
                request = asyncio.create_task(client.post(f'/api/courses/{cid}/generate', json={'expected_revision': 1, 'unit_id': 'unit-1'}))
                await asyncio.wait_for(entered.wait(), 3)
                with self.app.state.database.connection() as db:
                    row = db.execute("SELECT id,partial_json FROM jobs WHERE status='running'").fetchone()
                    jid, partial = row['id'], json.loads(row['partial_json'])
                (await client.post('/api/jobs/' + jid + '/cancel')).raise_for_status()
                await asyncio.wait_for(request, 3)
                job = (await client.get('/api/jobs/' + jid)).json()
                self.assertEqual(job['status'], 'cancelled')
                self.assertEqual(job['partial']['question_focus_plan'], partial['question_focus_plan'])
                self.assertEqual(set(job['partial']['questions']), {'mcq'})
                self.assertEqual(set(job['partial']['stage_focus']), {'mcq', 'cloze'})
        asyncio.run(scenario())
        self.assertEqual(self.editor(cid)['revision'], 1)
        self.assertIsNone(self.editor(cid)['content']['units'][0]['data'])
