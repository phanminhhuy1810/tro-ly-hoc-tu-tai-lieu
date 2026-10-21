import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient
import httpx

from study_backend.app import create_app
from study_backend.gemini import ProviderError
from study_backend.models import ChatReply, LessonReading
from study_backend.providers import Choice, ProviderRegistry
from test_slice import SliceFixture, TestProvider


class NamedProvider(TestProvider):
    def __init__(self, name):
        super().__init__()
        self.model, self.ready, self.enabled = name, True, True

    def metadata(self): return {'provider': 'explicit_test_adapter', 'model': self.model}
    async def status(self): return {**self.metadata(), 'ready': self.ready}


class ProviderTests(SliceFixture):
    def setUp(self):
        self.temp = TemporaryDirectory()
        root = Path(self.temp.name)
        self.a, self.b, self.disabled = [NamedProvider(x) for x in ['model-a', 'model-b', 'model-disabled']]
        self.disabled.enabled = False
        self.provider = self.a
        self.registry = ProviderRegistry([Choice('a', 'Local A', self.a), Choice('b', 'Remote B', self.b, True),
                                          Choice('disabled', 'Disabled', self.disabled)], 'a')
        self.app = create_app(root / 'data.sqlite', root / 'sources', provider_registry=self.registry, economy_enabled=False)
        self.client = TestClient(self.app, base_url='http://127.0.0.1')
        self.owner = self.client.post('/api/session').json()['id']

    def choose(self, model_id, revision=0, external=True, client=None):
        return (client or self.client).put('/api/ai/selection', json={'model_id': model_id, 'expected_revision': revision, 'allow_external': external})

    def test_catalog_and_selection_are_private_versioned_and_survive_restart(self):
        self.assertEqual(TestClient(self.app, base_url='http://127.0.0.1').get('/api/ai/models').status_code, 401)
        peer = TestClient(self.app, base_url='http://127.0.0.1'); peer.post('/api/session')
        self.choose('b').raise_for_status()
        self.assertEqual(self.client.get('/api/ai/models').json()['selected_model_id'], 'b')
        self.assertEqual(peer.get('/api/ai/models').json()['selected_model_id'], 'a')
        self.assertEqual(self.choose('a').status_code, 409)
        restored = ProviderRegistry(list(self.registry.choices.values()), 'a'); restored.database = self.app.state.database
        self.assertEqual(restored.preference(self.owner)['model_id'], 'b')
        self.assertEqual(self.client.get('/api/status').json()['ai']['model'], 'model-b')
        peer.close()

    def test_liveness_does_not_probe_or_depend_on_selected_model_readiness(self):
        async def unavailable():raise AssertionError('liveness must not contact a provider')
        self.a.status=unavailable;self.a.ready=False
        response=self.client.get('/api/health');response.raise_for_status()
        self.assertEqual(response.json(),{'backend':True,'provider_health_checked':False})
        self.assertEqual(self.registry.preference(self.owner)['model_id'],'a')

    def test_unknown_disabled_unavailable_and_unconfirmed_external_choices_do_not_change_preference(self):
        self.assertEqual(self.choose('http://attacker.test').status_code, 422)
        self.assertEqual(self.choose('disabled').status_code, 503)
        self.assertEqual(self.choose('b', external=False).status_code, 422)
        self.b.ready = False
        self.assertEqual(self.choose('b').status_code, 503)
        self.assertEqual(self.client.get('/api/ai/models').json()['selected_model_id'], 'a')
        self.assertEqual(self.client.put('/api/ai/selection', json={'model_id': 'a', 'expected_revision': 0, 'endpoint': 'https://evil.test'}).status_code, 422)

    def test_selected_model_generates_without_mutating_source_or_old_course(self):
        course = self.course(); old = self.client.get('/api/courses/' + course['id']).json()
        a_calls = self.a.calls
        self.choose('b').raise_for_status()
        value = self.job(self.client.post('/api/courses/' + course['id'] + '/chat', json={'unit_id': 'unit-1', 'message': 'Explain from source'}))
        self.assertEqual(value['text'], 'Gợi ý từ nguồn test')
        self.assertEqual(self.a.calls, a_calls)
        self.assertEqual(self.b.calls, 1)
        self.assertEqual(self.client.get('/api/courses/' + course['id']).json(), old)

    def test_old_quote_cannot_authorize_new_model_and_failure_refunds_without_fallback(self):
        course = self.course(); self.app.state.economy.enabled = True
        path = '/api/courses/' + course['id'] + '/chat'; body = {'unit_id': 'unit-1', 'message': 'Hint'}
        quote = self.client.post(path, json=body).json()['detail']
        a_calls = self.a.calls
        self.choose('b').raise_for_status()
        self.assertEqual(self.client.post(path, json=body, headers={'Coin-Quote-Id': quote['quote_id']}).status_code, 409)
        self.assertEqual(self.b.calls, 0)
        quote = self.client.post(path, json=body).json()['detail']
        self.assertEqual(quote['model'], 'model-b')
        async def quota(*args):
            self.b.calls += 1
            raise ProviderError('RATE_LIMITED', 'Quota exhausted', True)
        self.b.generate = quota
        response = self.client.post(path, json=body, headers={'Coin-Quote-Id': quote['quote_id'], 'Idempotency-Key': 'new-model-confirmed'})
        response.raise_for_status()
        job = self.client.get('/api/jobs/' + response.json()['job_id']).json()
        self.assertEqual(job['status'], 'failed')
        self.assertEqual(job['provider']['model'], 'model-b')
        self.assertEqual(job['error']['code'], 'RATE_LIMITED')
        wallet = self.client.get('/api/wallet').json()
        self.assertEqual((wallet['balance'], wallet['held']), (20, 0))
        self.assertEqual(self.a.calls, a_calls)

    def test_switch_during_running_job_keeps_the_original_model(self):
        course = self.course(); original = self.a.generate
        async def scenario():
            entered, release = asyncio.Event(), asyncio.Event()
            async def blocked(schema, instruction, fragments):
                if schema is ChatReply:
                    entered.set(); await release.wait()
                return await original(schema, instruction, fragments)
            self.a.generate = blocked
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://127.0.0.1', cookies=self.client.cookies) as client:
                pending = asyncio.create_task(client.post('/api/courses/' + course['id'] + '/chat', json={'unit_id': 'unit-1', 'message': 'Pin this request'}))
                await asyncio.wait_for(entered.wait(), 3)
                response = await client.put('/api/ai/selection', json={'model_id': 'b', 'expected_revision': 0, 'allow_external': True})
                response.raise_for_status(); release.set()
                completed = await asyncio.wait_for(pending, 3)
                job = (await client.get('/api/jobs/' + completed.json()['job_id'])).json()
                self.assertEqual(job['status'], 'succeeded')
                self.assertEqual(job['provider']['model'], 'model-a')
                self.assertEqual(self.b.calls, 0)
                self.assertEqual((await client.get('/api/status')).json()['ai']['model'], 'model-b')
        asyncio.run(scenario())

    def test_partial_retry_keeps_stage_provenance_when_switching_models(self):
        source = self.source()
        source = self.client.post(f"/api/sources/{source['id']}/review", json={'expected_revision': 1, 'texts': [f['text'] for f in source['fragments']]}).json()
        plan = self.job(self.client.post('/api/plans', json=self.preferences(source)))['plan_id']
        course_id = self.client.post('/api/plans/' + plan + '/approve', json={'expected_revision': 1}).json()['course_id']
        original = self.a.generate
        async def reading_only(schema, *args):
            from study_backend.chapter_context import ChapterBrief
            if schema in {ChapterBrief, LessonReading}: return await original(schema, *args)
            raise ProviderError('PROVIDER_TIMEOUT', 'Test stopped after saved reading')
        self.a.generate = reading_only
        response = self.client.post('/api/courses/' + course_id + '/generate', json={'expected_revision': 1, 'unit_id': 'unit-1'})
        job_id = response.json()['job_id']; job = self.client.get('/api/jobs/' + job_id).json()
        self.assertEqual(job['status'], 'failed')
        self.choose('b').raise_for_status()
        self.job(self.client.post('/api/courses/' + course_id + '/generate', json={'expected_revision': 1, 'unit_id': 'unit-1', 'resume_job_id': job_id}))
        unit = self.client.get('/api/courses/' + course_id + '/editor').json()['content']['units'][0]
        origins = unit['generation']['stage_providers']
        self.assertEqual(origins['reading']['model'], 'model-a')
        self.assertEqual(origins['mcq']['model'], 'model-b')
        self.assertEqual(unit['generation']['resumed_from_job_id'], job_id)
