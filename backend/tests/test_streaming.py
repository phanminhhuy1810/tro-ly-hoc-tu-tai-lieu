"""Stream framing, draft privacy and cancellation, with explicit test transports."""
import asyncio
import copy
import json
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from study_backend.ai import LocalAI, KaggleAI
from study_backend.gemini import GeminiAI, ProviderError
from study_backend.job_progress import json_text_prefix
from study_backend.models import ChatReply
from test_slice import SliceFixture


class Wire(httpx.AsyncByteStream):
    def __init__(self, parts, gate=None):
        self.parts, self.gate, self.closed = parts, gate, False
        self.started = asyncio.Event()
    async def __aiter__(self):
        for index, part in enumerate(self.parts):
            yield part
            if index == 0:
                self.started.set()
                if self.gate: await self.gate.wait()
    async def aclose(self): self.closed = True


class Progress:
    def __init__(self): self.parts, self.stats, self.fallbacks = [], {}, 0
    def chunk(self, text):
        if text: self.parts.append(text)
    def usage(self, value): self.stats.update(value)
    def fallback(self): self.fallbacks += 1


def gemini_packet(text='', finish=None, **extra):
    candidate = {'content': {'parts': [{'text': text}]}}
    if finish: candidate['finishReason'] = finish
    return ('data: ' + json.dumps({'candidates': [candidate], **extra}, ensure_ascii=False) + '\r\n\r\n').encode()


class TransportStreamingTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, ai, handler, progress):
        client_type = httpx.AsyncClient
        def client(*args, **kwargs): return client_type(*args, **kwargs, transport=httpx.MockTransport(handler))
        with patch('httpx.AsyncClient', client):
            return await ai.generate_stream(ChatReply, 'Explain the supplied source', [{'id': 'f1', 'text': 'IPv4 has 32 bits.'}], progress)

    async def test_gemini_emits_before_finish_handles_utf8_and_keeps_key_in_header(self):
        gate = asyncio.Event(); progress = Progress(); requests = []
        raw = json.dumps({'text': 'IPv4 có 32 bit. 🦊', 'source_refs': ['f1'], 'needs_more_source': False}, ensure_ascii=False)
        first = gemini_packet(raw[:20]); second = gemini_packet(raw[20:], 'STOP', usageMetadata={'promptTokenCount': 8, 'candidatesTokenCount': 12})
        split = second.index('🦊'.encode()) + 1
        wire = Wire([first, second[:split], second[split:]], gate)
        def handler(request):
            requests.append(request)
            self.assertTrue(request.url.path.endswith(':streamGenerateContent'))
            self.assertEqual(request.url.params.get('alt'), 'sse')
            self.assertNotIn('key=', str(request.url))
            self.assertEqual(request.headers['x-goog-api-key'], 'test-secret')
            return httpx.Response(200, stream=wire)
        pending = asyncio.create_task(self.exercise(GeminiAI(api_key='test-secret', enabled=True), handler, progress))
        await wire.started.wait(); self.assertFalse(pending.done())
        self.assertEqual(progress.parts, [raw[:20]])
        gate.set(); value = await pending
        self.assertEqual(value['text'], 'IPv4 có 32 bit. 🦊')
        self.assertEqual(''.join(progress.parts), raw)
        self.assertEqual(progress.stats['output_tokens'], 12)
        self.assertTrue(wire.closed); self.assertEqual(len(requests), 1)

    async def test_gemini_partial_safety_quota_invalid_refs_and_broken_frame_never_commit_or_retry(self):
        raw = json.dumps({'text': 'Draft', 'source_refs': ['f1'], 'needs_more_source': False})
        cases = [(200, gemini_packet(raw)), (200, gemini_packet(raw, 'MAX_TOKENS')),
                 (200, gemini_packet(raw, 'SAFETY')), (429, b'{"error":"test-secret"}'),
                 (200, gemini_packet(raw.replace('f1', 'foreign'), 'STOP')), (200, b'data: invalid\n\n')]
        for status, data in cases:
            calls = []
            def handler(request):
                calls.append(request)
                return httpx.Response(status, stream=Wire([data]))
            with self.subTest(status=status, data=data), self.assertRaises((ProviderError, ValueError)) as caught:
                await self.exercise(GeminiAI(api_key='test-secret', enabled=True), handler, Progress())
            self.assertEqual(len(calls), 1)
            self.assertNotIn('test-secret', str(caught.exception))

    async def test_ollama_and_kaggle_use_ndjson_one_protocol_fallback_and_provider_metrics(self):
        for ai in [LocalAI(), KaggleAI({'endpoint': 'https://fixture.ngrok-free.dev', 'username': 'qa', 'password': 'a'*32, 'model': 'fixture'})]:
            ai.model = 'fixture'; calls = []; progress = Progress()
            raw = json.dumps({'text': '32 bits', 'source_refs': ['f1'], 'needs_more_source': False})
            def handler(request):
                if request.url.path.endswith('/api/tags'): return httpx.Response(200, json={'models': [{'name': 'fixture'}]})
                body = json.loads(request.content); calls.append(body)
                self.assertTrue(body['stream']); self.assertFalse(body['think'])
                if 'format' in body:
                    return httpx.Response(501, json={'error': 'structured output is unavailable'})
                packets = [{'message': {'content': raw[:15]}, 'done': False},
                           {'message': {'content': raw[15:]}, 'done': True, 'done_reason': 'stop',
                            'eval_count': 20, 'load_duration': 1234567, 'eval_duration': 9876543}]
                return httpx.Response(200, stream=Wire([(json.dumps(p)+'\n').encode() for p in packets]))
            with self.subTest(provider=ai.provider_id):
                value = await self.exercise(ai, handler, progress)
                self.assertEqual(value['text'], '32 bits')
                self.assertEqual(len(calls), 2); self.assertEqual(progress.fallbacks, 1)
                self.assertEqual(progress.stats['load_duration_ns'], 1234567)
                self.assertEqual(progress.stats['output_tokens'], 20)

    async def test_ollama_does_not_retry_auth_quota_midstream_error_or_eof_without_done(self):
        for status, data in [(401, b'{}'), (429, b'{}'), (200, b'{"error":"test-secret"}\n'),
                             (200, b'{"message":{"content":"{}"},"done":false}\n')]:
            ai = LocalAI(); ai.model = 'fixture'; calls = []
            def handler(request):
                if request.url.path.endswith('/api/tags'): return httpx.Response(200, json={'models': [{'name': 'fixture'}]})
                calls.append(request); return httpx.Response(status, stream=Wire([data]))
            with self.subTest(status=status), self.assertRaises(ProviderError) as caught:
                await self.exercise(ai, handler, Progress())
            self.assertEqual(len(calls), 1); self.assertNotIn('test-secret', str(caught.exception))

    async def test_ollama_incomplete_final_retains_safe_metrics_without_accepting_or_retrying_output(self):
        raw=json.dumps({'text':'Complete-looking JSON','source_refs':['f1'],'needs_more_source':False})
        for reason,code,safe in [('length','OUTPUT_LIMIT_REACHED','length'),
                                 ({'credential':'test-secret'},'INCOMPLETE_OUTPUT','unknown')]:
            ai=LocalAI();ai.model='fixture';calls=[];progress=Progress()
            def handler(request):
                if request.url.path.endswith('/api/tags'):return httpx.Response(200,json={'models':[{'name':'fixture'}]})
                calls.append(request)
                packet={'message':{'content':raw},'done':True,'done_reason':reason,'eval_count':4500,'eval_duration':1234567}
                return httpx.Response(200,stream=Wire([(json.dumps(packet)+'\n').encode()]))
            with self.subTest(reason=reason),self.assertRaises(ProviderError) as caught:
                await self.exercise(ai,handler,progress)
            self.assertEqual(caught.exception.code,code)
            self.assertEqual(len(calls),1);self.assertEqual(progress.stats['output_tokens'],4500)
            self.assertEqual(progress.stats['eval_duration_ns'],1234567)
            self.assertEqual(progress.stats['provider_finish_reason'],safe)
            self.assertNotIn('test-secret',str(caught.exception));self.assertNotIn('test-secret',json.dumps(progress.stats))

    async def test_cancelling_a_native_request_closes_each_provider_stream(self):
        for ai in [GeminiAI(api_key='test-secret', enabled=True), LocalAI()]:
            gate = asyncio.Event(); ai.model = 'fixture' if isinstance(ai, LocalAI) else ai.model
            data = gemini_packet('{"text":"Draft') if isinstance(ai, GeminiAI) else b'{"message":{"content":"{\\"text\\":\\"Draft"},"done":false}\n'
            wire = Wire([data, data], gate)
            def handler(request):
                if request.url.path.endswith('/api/tags'): return httpx.Response(200, json={'models': [{'name': 'fixture'}]})
                return httpx.Response(200, stream=wire)
            pending = asyncio.create_task(self.exercise(ai, handler, Progress()))
            await wire.started.wait(); pending.cancel()
            with self.assertRaises(asyncio.CancelledError): await pending
            self.assertTrue(wire.closed)

    def test_preview_only_reads_root_text_and_never_partial_unicode_or_nested_answer(self):
        text = 'Một ý "đúng"\n🦊'
        raw = json.dumps({'source_refs': ['f1'], 'text': text}, ensure_ascii=True)
        prefixes = [json_text_prefix(raw[:i]) for i in range(len(raw) + 1)]
        self.assertTrue(all(text.startswith(v) for v in prefixes))
        self.assertEqual(prefixes[-1], text)
        self.assertEqual(json_text_prefix('{"question":{"text":"hidden answer"},"answer":"secret"}'), '')
        self.assertEqual(json_text_prefix('{"text":"x\\uD83D'), 'x')


class JobStreamingTests(SliceFixture):
    def test_failed_job_keeps_finish_metrics_without_secret_or_unvalidated_preview(self):
        course=self.course();seen=[]
        async def interrupted(schema,instruction,fragments,progress):
            seen.append(schema)
            progress.chunk('{"text":"unvalidated draft"}')
            progress.usage({'output_tokens':4500,'provider_finish_reason':'length','eval_duration_ns':1234567})
            progress.usage({'api_key':'test-secret','provider_finish_reason':{'key':'test-secret'}})
            raise ProviderError('OUTPUT_LIMIT_REACHED','Model reached its output limit.')
        self.provider.generate_stream=interrupted
        response=self.client.post('/api/courses/'+course['id']+'/chat',json={'unit_id':'unit-1','message':'Giải thích nguồn.'})
        response.raise_for_status();job=self.client.get('/api/jobs/'+response.json()['job_id']).json()
        self.assertEqual(job['status'],'failed');self.assertEqual(job['error']['code'],'OUTPUT_LIMIT_REACHED')
        self.assertEqual(len(seen),1);self.assertIsNone(job['progress']['preview'])
        request=job['progress']['requests'][0]
        self.assertEqual(request['usage']['provider_finish_reason'],'length')
        self.assertEqual(request['usage']['output_tokens'],4500)
        self.assertEqual(request['usage']['eval_duration_ns'],1234567)
        self.assertGreaterEqual(request['elapsed_ms'],0)
        self.assertEqual(request['phase'],'failed');self.assertNotIn('test-secret',json.dumps(job))
        self.assertEqual(self.client.get('/api/courses/'+course['id']+'/editor').json(),course)

    def test_internal_validation_audit_survives_real_progress_storage_and_filters_untrusted_values(self):
        from study_backend import job_progress
        from study_backend.generation_contract import validated_generation
        from study_backend.models import QUESTION_DRAFTS
        owner=self.client.post('/api/session').json()['id'];jid='validation-audit-fixture'
        with self.app.state.database.connection(write=True) as db:
            db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                       (jid,owner,'lesson','{}','running',1,1,None,'{}',None,job_progress.stamp(),job_progress.stamp()))
            job_progress.initial(db,jid)
        reporter=job_progress.Reporter(self.app.state.database,jid,'lesson');progress=reporter.request('OrderingDraft',True)
        fragments=[{'id':'ref','text':'Procedure: (1) read the prefix; (2) calculate host bits.'}]
        value={'question':{'kind':'ordering','prompt':'Arrange','options':['2. calculate host bits','1. read the prefix'],
                           'explanation':'Use source steps.','source_refs':['ref']},'reason':''}
        raw=json.dumps(value)[:-1]+',}'
        result=validated_generation(QUESTION_DRAFTS['ordering'],raw,progress,fragments)
        progress.usage({'input_tokens':10,'api_key':'do-not-store','raw_json_sha256':'bad',
                        'ordering_answer_derived':True,'ordering_step_labels_removed':900,
                        'ordering_answer_method':'untrusted-provider-method'})
        cloze=reporter.request('ClozeDraft',True)
        raw_cloze=json.dumps({'question':{'kind':'cloze','prompt':'IPv4 has32 bits.','answer':'32','explanation':'Source statement.','source_refs':['ref']},'reason':''})
        # Use a clear token boundary in both the source and the model statement.
        raw_cloze=raw_cloze.replace('has32','has 32')
        validated_generation(QUESTION_DRAFTS['cloze'],raw_cloze,cloze,[{'id':'ref','text':'IPv4 has 32 bits.'}])
        cloze.received()
        progress.received()
        with self.app.state.database.connection() as db:
            snapshot=job_progress.read(db,jid)
            stored=snapshot['requests'][0]['usage']
            cloze_stored=snapshot['requests'][1]['usage']
        self.assertEqual(cloze_stored['cloze_source_mask_derived'],1)
        self.assertEqual(len(cloze_stored['cloze_statement_sha256']),64)
        self.assertEqual(result.question.answer,[1,0])
        self.assertEqual(stored['json_trailing_commas_removed'],1)
        self.assertEqual(stored['ordering_answer_derived'],1)
        self.assertEqual(stored['ordering_step_labels_removed'],2)
        self.assertEqual(stored['ordering_answer_method'],'explicit_scoped_source_steps_v2')
        self.assertEqual(len(stored['raw_json_sha256']),64)
        self.assertEqual(len(stored['normalized_json_sha256']),64)
        self.assertEqual(stored['input_tokens'],10)
        self.assertNotIn('api_key',stored)

    def install_stream(self, ready, release, fail=False, foreign=False):
        self.stream_closed = False
        async def generate_stream(schema, instruction, fragments, progress):
            raw = json.dumps({'text': 'Một gợi ý từ nguồn. 🦊', 'source_refs': ['foreign'] if foreign else [f['id'] for f in fragments], 'needs_more_source': False}, ensure_ascii=False)
            try:
                progress.chunk(raw[:30]); ready.set(); await release.wait()
                if fail: raise ProviderError('CONNECTION_FAILED', 'Fixture connection lost', True)
                progress.chunk(raw[30:]); return json.loads(raw)
            finally: self.stream_closed = True
        self.provider.generate_stream = generate_stream

    def test_partial_text_is_observable_before_validation_private_and_not_in_history(self):
        course = self.course(); path = '/api/courses/' + course['id']
        async def scenario():
            ready, release = asyncio.Event(), asyncio.Event(); self.install_stream(ready, release)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://127.0.0.1', cookies=self.client.cookies) as client:
                pending = asyncio.create_task(client.post(path + '/chat', json={'unit_id': 'unit-1', 'message': 'Explain'}))
                await asyncio.wait_for(ready.wait(), 2)
                with self.app.state.database.connection() as db: job_id = db.execute("SELECT id FROM jobs WHERE status='running'").fetchone()[0]
                value = (await client.get('/api/jobs/' + job_id)).json()
                self.assertFalse(value['progress']['preview']['validated'])
                self.assertTrue(value['progress']['preview']['text'])
                self.assertIsNone(value['result'])
                self.assertEqual([m['role'] for m in (await client.get(path + '/chat')).json()], ['user'])
                snapshot = await client.get('/api/jobs/' + job_id + '/events?once=true')
                self.assertIn('event: snapshot', snapshot.text)
                self.assertNotIn('answer', json.dumps(value['progress']))
                cursor = value['progress']['version']
                self.assertEqual((await client.get('/api/jobs/' + job_id + '/events?once=true', headers={'Last-Event-ID': str(cursor)})).status_code, 200)
                self.assertEqual((await client.get('/api/jobs/' + job_id + '/events?once=true', headers={'Last-Event-ID': '9999999'})).status_code, 409)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://127.0.0.1') as other:
                    await other.post('/api/session')
                    self.assertEqual((await other.get('/api/jobs/' + job_id + '/events?once=true')).status_code, 404)
                release.set(); await pending
                final = (await client.get('/api/jobs/' + job_id)).json()
                self.assertEqual(final['status'], 'succeeded'); self.assertIsNone(final['progress']['preview'])
                self.assertGreater(final['progress']['version'], cursor)
                self.assertEqual(final['result']['text'], 'Một gợi ý từ nguồn. 🦊')
        asyncio.run(scenario())

    def test_cancel_closes_upstream_clears_preview_releases_coin_and_prevents_late_answer(self):
        course = self.course(); path = '/api/courses/' + course['id']; self.app.state.economy.enabled = True
        async def scenario():
            ready, release = asyncio.Event(), asyncio.Event(); self.install_stream(ready, release)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://127.0.0.1', cookies=self.client.cookies) as client:
                body = {'unit_id': 'unit-1', 'message': 'Explain'}; headers = {'Idempotency-Key': 'cancel-stream'}
                quote = (await client.post(path + '/chat', json=body, headers=headers)).json()['detail']
                headers['Coin-Quote-Id'] = quote['quote_id']
                pending = asyncio.create_task(client.post(path + '/chat', json=body, headers=headers))
                await asyncio.wait_for(ready.wait(), 2)
                with self.app.state.database.connection() as db: job_id = db.execute("SELECT id FROM jobs WHERE status='running'").fetchone()[0]
                self.assertEqual((await client.get('/api/wallet')).json()['held'], 1)
                await client.post('/api/jobs/' + job_id + '/cancel')
                await asyncio.wait_for(pending, 2); release.set()
                self.assertTrue(self.stream_closed)
                value = (await client.get('/api/jobs/' + job_id)).json()
                self.assertEqual(value['status'], 'cancelled'); self.assertIsNone(value['progress']['preview'])
                self.assertEqual(value['progress']['phase'], 'cancelled')
                self.assertEqual((await client.get('/api/wallet')).json()['balance'], 20)
                self.assertEqual((await client.get('/api/wallet')).json()['held'], 0)
                self.assertEqual([m['role'] for m in (await client.get(path + '/chat')).json()], ['user'])
        asyncio.run(scenario())

    def test_invalid_final_source_discards_visible_draft_without_saving_answer(self):
        course = self.course(); path = '/api/courses/' + course['id']
        async def scenario():
            ready, release = asyncio.Event(), asyncio.Event(); self.install_stream(ready, release, foreign=True)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://127.0.0.1', cookies=self.client.cookies) as client:
                pending = asyncio.create_task(client.post(path + '/chat', json={'unit_id': 'unit-1', 'message': 'Explain'}))
                await ready.wait(); release.set(); response = await pending
                value = (await client.get('/api/jobs/' + response.json()['job_id'])).json()
                self.assertEqual(value['status'], 'failed'); self.assertIsNone(value['progress']['preview'])
                self.assertIsNone(value['result'])
                self.assertEqual([m['role'] for m in (await client.get(path + '/chat')).json()], ['user'])
        asyncio.run(scenario())

    def test_active_exam_masks_progress_and_result_then_restores_access(self):
        course = self.course(); path = '/api/courses/' + course['id']
        async def scenario():
            ready, release = asyncio.Event(), asyncio.Event(); self.install_stream(ready, release)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://127.0.0.1', cookies=self.client.cookies) as client:
                pending = asyncio.create_task(client.post(path + '/chat', json={'unit_id': 'unit-1', 'message': 'Explain'}))
                await ready.wait()
                with self.app.state.database.connection() as db: job_id = db.execute("SELECT id FROM jobs WHERE status='running'").fetchone()[0]
                exam = (await client.post(path + '/sessions', json={'expected_revision': 2, 'unit_id': 'unit-1', 'exercise': 'test'})).json()
                event = await client.get('/api/jobs/' + job_id + '/events?once=true')
                value = json.loads(event.text.split('data: ', 1)[1])
                self.assertTrue(value['feedback_deferred']); self.assertIsNone(value['progress']['preview'])
                release.set(); await pending
                self.assertIsNone((await client.get('/api/jobs/' + job_id)).json()['result'])
                await client.post('/api/sessions/' + exam['id'] + '/cancel')
                self.assertTrue((await client.get('/api/jobs/' + job_id)).json()['result']['text'])
        asyncio.run(scenario())

    def test_stream_rechecks_auth_and_closes_on_cookie_expiry(self):
        course = self.course(); path = '/api/courses/' + course['id']
        async def scenario():
            ready, release = asyncio.Event(), asyncio.Event(); self.install_stream(ready, release)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://127.0.0.1', cookies=self.client.cookies) as client:
                pending = asyncio.create_task(client.post(path + '/chat', json={'unit_id': 'unit-1', 'message': 'Explain'}))
                await ready.wait()
                with self.app.state.database.connection() as db: job_id = db.execute("SELECT id FROM jobs WHERE status='running'").fetchone()[0]
                events = asyncio.create_task(client.get('/api/jobs/' + job_id + '/events'))
                await asyncio.sleep(0.1)
                with self.app.state.database.connection(write=True) as db: db.execute('UPDATE auth_sessions SET expires_at=0')
                response = await asyncio.wait_for(events, 2)
                self.assertIn('event: session_expired', response.text)
                release.set(); await pending
        asyncio.run(scenario())

    def test_deadline_clears_stream_without_turning_it_into_a_saved_response(self):
        course = self.course(); path = '/api/courses/' + course['id']
        self.app.state.jobs.timeout_seconds = 0.05
        async def scenario():
            ready, release = asyncio.Event(), asyncio.Event(); self.install_stream(ready, release)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://127.0.0.1', cookies=self.client.cookies) as client:
                response = await client.post(path + '/chat', json={'unit_id': 'unit-1', 'message': 'Explain'})
                value = (await client.get('/api/jobs/' + response.json()['job_id'])).json()
                self.assertEqual(value['status'], 'failed'); self.assertEqual(value['error']['code'], 'JOB_TIMEOUT')
                self.assertIsNone(value['progress']['preview']); self.assertTrue(self.stream_closed)
        asyncio.run(scenario())

    def test_lesson_reports_actual_planned_and_saved_counts_instead_of_fixed_five(self):
        source = self.source()
        source = self.client.post('/api/sources/' + source['id'] + '/review', json={'expected_revision': 1, 'texts': [f['text'] for f in source['fragments']]}).json()
        prefs = {**self.preferences(source), 'question_types': ['mcq'], 'question_count': 1}
        plan_id = self.job(self.client.post('/api/plans', json=prefs))['plan_id']
        course_id = self.client.post('/api/plans/' + plan_id + '/approve', json={'expected_revision': 1}).json()['course_id']
        response = self.client.post('/api/courses/' + course_id + '/generate', json={'expected_revision': 1, 'unit_id': 'unit-1'})
        response.raise_for_status()
        value = self.client.get('/api/jobs/' + response.json()['job_id']).json()
        self.assertEqual(value['progress']['planned_stages'], 3)  # chapter + reading + one question
        self.assertEqual(value['progress']['saved_stages'], 3)
        self.assertEqual(value['progress']['reused_stages'], 0)
        self.assertEqual(len(value['progress']['requests']), 3)

    def test_room_started_midstream_hides_draft_and_final_until_room_closes(self):
        course = self.course(); path = '/api/courses/' + course['id']
        async def scenario():
            ready, release = asyncio.Event(), asyncio.Event(); self.install_stream(ready, release)
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(transport=transport, base_url='http://127.0.0.1', cookies=self.client.cookies) as client, httpx.AsyncClient(transport=transport, base_url='http://127.0.0.1') as peer:
                pending = asyncio.create_task(client.post(path + '/chat', json={'unit_id': 'unit-1', 'message': 'Explain'}))
                await ready.wait()
                with self.app.state.database.connection() as db: job_id = db.execute("SELECT id FROM jobs WHERE status='running'").fetchone()[0]
                await peer.post('/api/session')
                response = await client.post('/api/rooms', json={'course_id': course['id'], 'expected_revision': 2, 'unit_ids': ['unit-1'], 'question_count': 1, 'seconds_per_question': 30, 'nickname': 'Host'}, headers={'Idempotency-Key': 'midstream-room'})
                response.raise_for_status(); room = response.json()
                await peer.post('/api/rooms/join', json={'code': room['join_code'], 'nickname': 'Peer'})
                room_path = '/api/rooms/' + room['room_id']
                current = (await client.get(room_path)).json()
                response = await client.post(room_path + '/start', json={'expected_event_index': current['event_index']}, headers={'Idempotency-Key': 'start-midstream'})
                response.raise_for_status()
                value = (await client.get('/api/jobs/' + job_id)).json()
                self.assertTrue(value['feedback_deferred']); self.assertIsNone(value['progress']['preview'])
                release.set(); await pending
                self.assertIsNone((await client.get('/api/jobs/' + job_id)).json()['result'])
                current = (await client.get(room_path)).json()
                await client.post(room_path + '/close', json={'expected_event_index': current['event_index']}, headers={'Idempotency-Key': 'close-midstream'})
                self.assertTrue((await client.get('/api/jobs/' + job_id)).json()['result']['text'])
        asyncio.run(scenario())

    def test_two_stream_limit_releases_slots_after_completion(self):
        course = self.course(); path = '/api/courses/' + course['id']
        async def scenario():
            ready, release = asyncio.Event(), asyncio.Event(); self.install_stream(ready, release)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://127.0.0.1', cookies=self.client.cookies) as client:
                pending = asyncio.create_task(client.post(path + '/chat', json={'unit_id': 'unit-1', 'message': 'Explain'}))
                await ready.wait()
                with self.app.state.database.connection() as db: job_id = db.execute("SELECT id FROM jobs WHERE status='running'").fetchone()[0]
                url = '/api/jobs/' + job_id + '/events'
                first = asyncio.create_task(client.get(url)); second = asyncio.create_task(client.get(url))
                await asyncio.sleep(0.1)
                self.assertEqual((await client.get(url + '?once=true')).status_code, 429)
                release.set(); await pending
                await asyncio.gather(first, second)
                self.assertEqual((await client.get(url + '?once=true')).status_code, 200)
        asyncio.run(scenario())

    def test_restart_clears_unverified_preview_and_never_restarts_model(self):
        from fastapi import BackgroundTasks
        from study_backend.app import create_app
        from study_backend import job_progress
        course = self.course()
        owner = self.client.post('/api/session').json()['id']
        jobs = self.app.state.jobs
        payload = {'course_id': course['id'], 'unit_id': 'unit-1', 'message': 'Interrupted fixture'}
        async def unexpected(job_id): self.fail('Restart reran model work')
        started = jobs.create(owner, 'chat', payload, BackgroundTasks(), unexpected, jobs.identity(None, 'chat', payload, owner))
        with self.app.state.database.connection(write=True) as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (started['job_id'],))
            progress = job_progress.read(db, started['job_id'])
            progress.update(phase='receiving', preview={'text': 'Unverified draft', 'validated': False})
            job_progress.write(db, started['job_id'], progress)
        calls = self.provider.calls
        restarted = create_app(self.app.state.database.path, self.temp.name + '/sources', provider=self.provider, economy_enabled=False)
        with TestClient(restarted, base_url='http://127.0.0.1', cookies=self.client.cookies) as client:
            value = client.get('/api/jobs/' + started['job_id']).json()
            self.assertEqual(value['status'], 'failed'); self.assertIsNone(value['progress']['preview'])
            self.assertEqual(value['progress']['phase'], 'failed')
            self.assertEqual(self.provider.calls, calls)
            self.assertTrue(client.get('/api/courses/' + course['id']).json()['content']['units'][0]['data'])
