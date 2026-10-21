"""Chapter-wide transport coverage and resumability, not a semantic accuracy score."""
import copy
import asyncio
import json
import unittest
from pathlib import Path
from unittest.mock import patch
import httpx

from fastapi.testclient import TestClient

from study_backend.app import create_app
from study_backend.chapter_context import ChapterBrief, partition, schedule, semantic
from study_backend.gemini import ProviderError
from study_backend.models import QUESTION_DRAFTS, LessonReading
from study_backend.source_context import fits
from test_slice import SliceFixture


class PartitionTests(unittest.TestCase):
    def test_oversized_unicode_excerpt_is_covered_exactly_including_tail_and_locations(self):
        text = ('Điều kiện áp dụng và công thức: x² + y².\n' * 900) + 'TAIL_PRINCIPLE'
        original = [{'id': 'page-1', 'text': text, 'locator': {'page': 27, 'type': 'pdf'}}]
        before = copy.deepcopy(original)
        chunks = partition(original)
        self.assertGreater(len(chunks), 3)
        spans = [span for c in chunks for span in c['ranges']]
        parts = [f for c in chunks for f in c['fragments']]
        self.assertEqual(''.join(f['text'] for f in parts), text)
        self.assertEqual(spans[0]['start'], 0); self.assertEqual(spans[-1]['end'], len(text))
        self.assertTrue(all(a['end'] == b['start'] for a, b in zip(spans, spans[1:])))
        self.assertTrue(all(fits(c['fragments']) for c in chunks))
        self.assertTrue(all(f['locator']['page'] == 27 for f in parts))
        self.assertEqual(original, before)
        tasks, root = schedule(chunks)
        self.assertEqual(len(tasks), len(chunks) * 2 - 1)
        ancestors = {task['id']: task for task in tasks}
        def leaves(key):
            task = ancestors[key]
            return [key] if task['kind'] == 'map' else [x for c in task['children'] for x in leaves(c)]
        self.assertEqual(set(leaves(root)), {f'map:{i}' for i in range(len(chunks))})

    def test_empty_or_duplicate_scope_is_rejected_instead_of_marked_read(self):
        for value in ([], [{'id':'a','text':'x'},{'id':'a','text':'y'}], [{'id':'a','text':''}]):
            with self.assertRaises(ValueError):partition(value)


class ChapterContextTests(SliceFixture):
    def draft(self, paragraphs=18, excluded=False):
        lines = [f'Ý {i}: IPv4 có 32 bit, prefix xác định phần network; '+('Giải thích nguyên lý và điều kiện dùng. ' * 12)
                 for i in range(paragraphs)]
        lines[-1] += ' TAIL_PRINCIPLE: host = tổng địa chỉ trừ network và broadcast.'
        if excluded:lines.append('PRIVATE_DO_NOT_SEND: phần chưa chọn.')
        source = self.client.post('/api/sources/text', json={'name':'chapter.txt','text':'\n'.join(lines)}).json()
        source = self.client.post(f"/api/sources/{source['id']}/review", json={'expected_revision':1,'texts':[f['text'] for f in source['fragments']]}).json()
        all_refs = [f['id'] for f in source['fragments']]
        prefs = {**self.preferences(source), 'fragment_ids':all_refs[:-1] if excluded else all_refs,
                 'excluded_fragment_ids':all_refs[-1:] if excluded else [], 'question_types':['mcq'],
                 'question_count':1, 'unlock_policy':'open'}
        plan = self.client.post('/api/plans/from-source-sections', json=prefs).json()
        course_id = self.client.post(f"/api/plans/{plan['id']}/approve", json={'expected_revision':1}).json()['course_id']
        return self.client.get(f'/api/courses/{course_id}/editor').json(), plan, source

    def generate(self, course, unit='unit-1', **kwargs):
        return self.client.post(f"/api/courses/{course['id']}/generate", json={'expected_revision':course['revision'],'unit_id':unit,**kwargs})

    def progress(self, course):
        return self.client.get(f"/api/courses/{course['id']}/chapter-context?unit_id=unit-1").json()

    def install_recording_provider(self):
        events=[]; original=self.provider.generate
        async def record(schema, instruction, fragments):
            events.append({'schema':schema,'instruction':instruction,'fragments':copy.deepcopy(fragments)})
            if schema is ChapterBrief:
                self.provider.calls += 1
                tail='TAIL_PRINCIPLE' if 'TAIL_PRINCIPLE' in json.dumps(fragments,ensure_ascii=False) else 'Phần đầu chương'
                return {'summary':'Phân tích đủ phần được gửi.', 'key_ideas':[tail],
                        'connections':['Prefix xác định số bit host, từ đó suy ra số địa chỉ.'],
                        'misconceptions':['Số địa chỉ không luôn bằng số host dùng được.'],
                        'question_targets':['Suy ra số host từ prefix trong tình huống đủ dữ kiện.'],
                        'source_refs':[f['id'] for f in fragments]}
            return await original(schema,instruction,fragments)
        self.provider.generate=record
        return events

    def finish_reading(self, course):
        for _ in range(20):
            result=self.job(self.generate(course))
            if not result.get('continuation_required'):return result
        self.fail('Finite chapter fixture did not finish')

    def test_all_selected_chapter_and_tail_read_before_any_question_without_sending_excluded_text(self):
        course,plan,source=self.draft(excluded=True)
        events=self.install_recording_provider()
        self.assertEqual(self.progress(course)['saved_stages'],0)
        self.finish_reading(course)
        first_question=next(i for i,e in enumerate(events) if e['schema'] is QUESTION_DRAFTS['mcq'])
        maps=[e for e in events[:first_question] if e['schema'] is ChapterBrief and 'chapter_analysis' not in str(e['fragments'][0]['locator'])]
        self.assertEqual({f['id'] for e in maps for f in e['fragments']}, set(plan['preferences']['fragment_ids']))
        self.assertTrue(any('TAIL_PRINCIPLE' in f['text'] for e in maps for f in e['fragments']))
        self.assertNotIn('PRIVATE_DO_NOT_SEND',json.dumps(events,default=str,ensure_ascii=False))
        question_event=events[first_question]
        self.assertIn('TAIL_PRINCIPLE',question_event['instruction'])
        self.assertTrue(set(f['id'] for f in question_event['fragments']) < set(plan['preferences']['fragment_ids']))
        state=self.progress(course)
        self.assertTrue(state['complete']);self.assertEqual(state['covered_fragments'],state['total_fragments'])
        self.assertEqual(state['covered_characters'],state['total_characters'])
        self.assertEqual(self.client.get(f"/api/courses/{course['id']}/editor").json()['content']['units'][0]['generation']['chapter_context'],state)

    def test_bounded_continuations_keep_revision_and_reuse_context_for_next_unit(self):
        course,_,_=self.draft();events=self.install_recording_provider()
        with patch('study_backend.chapter_context.MAX_READ_CALLS_PER_JOB',1):
            first=self.job(self.generate(course))
            self.assertTrue(first['continuation_required'])
            self.assertEqual(first['chapter_context']['read_parts'],1)
            self.assertFalse(any(e['schema'] is LessonReading or e['schema'] in QUESTION_DRAFTS.values() for e in events))
            current=self.client.get(f"/api/courses/{course['id']}/editor").json()
            self.assertEqual(current['revision'],1);self.assertTrue(all(not u['data'] for u in current['content']['units']))
            self.finish_reading(course)
        current=self.client.get(f"/api/courses/{course['id']}/editor").json();before=copy.deepcopy(current['content']['units'][0])
        reads=sum(e['schema'] is ChapterBrief for e in events)
        self.job(self.generate(current,'unit-2'))
        self.assertEqual(sum(e['schema'] is ChapterBrief for e in events),reads)
        self.assertEqual(self.client.get(f"/api/courses/{course['id']}/editor").json()['content']['units'][0],before)

    def test_failed_map_keeps_checkpoint_and_restart_resumes_only_unread_work(self):
        course,_,_=self.draft();events=self.install_recording_provider();original=self.provider.generate
        calls=0
        async def fail_second(schema,*args):
            nonlocal calls
            if schema is ChapterBrief:
                calls+=1
                if calls==2:raise ProviderError('CONNECTION_FAILED','Fixture disconnect',True)
            return await original(schema,*args)
        self.provider.generate=fail_second
        response=self.generate(course);jid=response.json()['job_id'];failed=self.client.get('/api/jobs/'+jid).json()
        self.assertEqual(failed['status'],'failed');self.assertEqual(failed['partial']['chapter_context']['read_parts'],1)
        self.assertIsNone(failed['partial']['reading'])
        first_map=copy.deepcopy(events[0]['fragments'])
        self.provider.generate=original
        self.client.close()
        restarted=create_app(self.app.state.database.path,Path(self.temp.name)/'sources',provider=self.provider,economy_enabled=False)
        self.client=TestClient(restarted,base_url='http://127.0.0.1',cookies=self.client.cookies)
        self.app=restarted
        before=len(events)
        result=self.job(self.generate(course,resume_job_id=jid))
        while result.get('continuation_required'):result=self.job(self.generate(course))
        self.assertTrue(self.progress(course)['complete'])
        self.assertFalse(any(e['schema'] is ChapterBrief and e['fragments']==first_map for e in events[before:]))
        self.assertEqual(self.client.get('/api/jobs/'+jid).json()['partial'],failed['partial'])

    def test_progress_private_and_cache_tampering_stops_generation(self):
        course,_,_=self.draft();self.install_recording_provider()
        with patch('study_backend.chapter_context.MAX_READ_CALLS_PER_JOB',1):self.job(self.generate(course))
        other=TestClient(self.app,base_url='http://127.0.0.1');other.post('/api/session')
        self.assertEqual(other.get(f"/api/courses/{course['id']}/chapter-context?unit_id=unit-1").status_code,404);other.close()
        context_id=self.progress(course)['context_id']
        with self.app.state.database.connection(write=True) as db:
            row=db.execute('SELECT nodes_json FROM chapter_contexts WHERE id=?',(context_id,)).fetchone()
            nodes=json.loads(row[0]);nodes['map:0']['brief']['key_ideas']=['tampered']
            db.execute('UPDATE chapter_contexts SET nodes_json=? WHERE id=?',(json.dumps(nodes),context_id))
        calls=self.provider.calls
        job=self.client.get('/api/jobs/'+self.generate(course).json()['job_id']).json()
        self.assertEqual(job['status'],'failed');self.assertEqual(self.provider.calls,calls)
        self.assertEqual(self.client.get(f"/api/courses/{course['id']}/editor").json()['revision'],1)

    def test_cancel_during_second_map_keeps_first_part_and_never_generates_a_question(self):
        course,_,_=self.draft();events=self.install_recording_provider();original=self.provider.generate
        async def scenario():
            entered=asyncio.Event();release=asyncio.Event();reads=0
            async def block_second(schema,*args):
                nonlocal reads
                if schema is ChapterBrief:
                    reads+=1
                    if reads==2:entered.set();await release.wait()
                return await original(schema,*args)
            self.provider.generate=block_second
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://127.0.0.1',cookies=self.client.cookies) as client:
                pending=asyncio.create_task(client.post(f"/api/courses/{course['id']}/generate",json={'expected_revision':1,'unit_id':'unit-1'}))
                await asyncio.wait_for(entered.wait(),3)
                with self.app.state.database.connection() as db:
                    jid=db.execute("SELECT id FROM jobs WHERE task='lesson' AND status='running'").fetchone()[0]
                job=(await client.get('/api/jobs/'+jid)).json()
                self.assertEqual(job['partial']['chapter_context']['read_parts'],1)
                (await client.post('/api/jobs/'+jid+'/cancel')).raise_for_status()
                await asyncio.wait_for(pending,3)
                current=(await client.get('/api/jobs/'+jid)).json()
                self.assertEqual(current['status'],'cancelled')
                self.assertEqual(current['partial']['chapter_context']['read_parts'],1)
                self.assertEqual((await client.get(f"/api/courses/{course['id']}/editor")).json()['revision'],1)
                self.assertFalse(any(e['schema'] is LessonReading or e['schema'] in QUESTION_DRAFTS.values() for e in events))
        asyncio.run(scenario())

    def test_unknown_map_citation_is_hard_failure_before_any_lesson_or_question(self):
        course,_,_=self.draft();original=self.provider.generate
        async def foreign(schema,*args):
            value=await original(schema,*args)
            if schema is ChapterBrief:value['source_refs']=['unapproved-source']
            return value
        self.provider.generate=foreign
        failed=self.client.get('/api/jobs/'+self.generate(course).json()['job_id']).json()
        self.assertEqual(failed['status'],'failed');self.assertEqual(failed['error']['code'],'SOURCE_REFERENCE_MISMATCH')
        self.assertEqual(failed['partial']['chapter_context']['read_parts'],0)
        self.assertIsNone(failed['partial']['reading']);self.assertEqual(failed['partial']['questions'],{})
        self.assertFalse(self.progress(course)['complete'])

    def test_new_reviewed_extraction_cannot_reuse_old_chapter_but_old_binding_remains(self):
        course,plan,source=self.draft(paragraphs=2);self.install_recording_provider();self.finish_reading(course)
        old=self.progress(course)
        changed=self.client.post(f"/api/sources/{source['id']}/review",json={'expected_revision':source['revision'],'texts':[f['text']+' Corrected premise.' for f in source['fragments']]}).json()
        prefs={**plan['preferences'],'fragment_ids':[f['id'] for f in changed['fragments']], 'expected_extraction_revision':changed['revision']}
        prefs.pop('extraction_revision')
        fresh=self.client.post('/api/plans/from-source-sections',json=prefs).json()
        cid=self.client.post(f"/api/plans/{fresh['id']}/approve",json={'expected_revision':1}).json()['course_id']
        new=self.progress({'id':cid})
        self.assertNotEqual(new['context_id'],old['context_id']);self.assertEqual(new['read_parts'],0)
        self.assertEqual(new['extraction_revision'],changed['revision'])
        self.assertEqual(self.progress(course),old)

    def test_intermediate_reading_releases_coin_and_does_not_consume_initial_lesson_quota(self):
        course,_,_=self.draft();self.install_recording_provider()
        economy=self.app.state.jobs.economy;economy.enabled=True
        economy.policy['initial_quota']['lesson']=0
        before=self.client.get('/api/wallet').json()
        with patch('study_backend.chapter_context.MAX_READ_CALLS_PER_JOB',1):
            body={'expected_revision':1,'unit_id':'unit-1'};path=f"/api/courses/{course['id']}/generate"
            headers={'Idempotency-Key':'chapter-paid-batch'}
            quoted=self.client.post(path,json=body,headers=headers)
            self.assertEqual(quoted.status_code,402)
            headers['Coin-Quote-Id']=quoted.json()['detail']['quote_id']
            result=self.job(self.client.post(path,json=body,headers=headers))
            self.assertTrue(result['continuation_required'])
        after=self.client.get('/api/wallet').json()
        self.assertEqual((after['balance'],after['held']),(before['balance'],0))
        with self.app.state.database.connection() as db:
            self.assertEqual(db.execute("SELECT status FROM ai_usage ORDER BY created_at DESC LIMIT 1").fetchone()[0],'released')

    def test_authored_cloze_can_apply_principle_without_quoting_source_sentence(self):
        course,plan,source=self.draft(paragraphs=2)
        self.install_recording_provider();original=self.provider.generate
        async def cloze(schema,instruction,fragments):
            if schema is QUESTION_DRAFTS['cloze']:
                self.assertIn('TỰ SOẠN',instruction)
                self.assertIn('BỐI CẢNH TOÀN CHƯƠNG',instruction)
                return {'question':{'kind':'cloze','prompt':'Một subnet /25 có 128 địa chỉ; bỏ network và broadcast thì dùng được ____ host.',
                    'answer':'126','explanation':'128 − 2 = 126 host.','source_refs':[fragments[0]['id']]},'reason':''}
            return await original(schema,instruction,fragments)
        self.provider.generate=cloze
        # New approved plan, preserving the earlier draft/history.
        prefs={**plan['preferences'],'source_id':source['id'],'question_types':['cloze'],'question_count':1}
        prefs.pop('extraction_revision');prefs['expected_extraction_revision']=source['revision']
        fresh=self.client.post('/api/plans/from-source-sections',json=prefs).json()
        cid=self.client.post(f"/api/plans/{fresh['id']}/approve",json={'expected_revision':1}).json()['course_id']
        self.finish_reading({'id':cid,'revision':1})
        lesson=self.client.get(f'/api/courses/{cid}/editor').json()['content']['units'][0]['data']
        self.assertEqual(lesson['questions'][0]['answer'],'126')
        self.assertNotIn(lesson['questions'][0]['prompt'],'\n'.join(f['text'] for f in source['fragments']))
        session=self.client.post(f'/api/courses/{cid}/sessions',json={'expected_revision':2,'unit_id':'unit-1'}).json()
        graded=self.client.post(f"/api/sessions/{session['id']}/answers",json={'item_id':session['questions'][0]['id'],'answer':'126'}).json()
        self.assertTrue(graded['correct']);self.assertEqual(graded['grading'],'fixed')
