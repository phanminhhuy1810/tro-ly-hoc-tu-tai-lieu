"""The free API pool, with fixture keys and a mock network only."""
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx

from study_backend.free_apis import FreePoolAI, json_text, private_config
from study_backend.gemini import ProviderError
from study_backend.models import ChatReply
from study_backend.providers import configured_registry

REPLY = {'text': 'Chào bạn', 'source_refs': [], 'needs_more_source': False}


def config(*providers, **extra):
    return {'members': [{'provider': p, 'api_key': 'fixture-' + p, 'models': [p + '-model']} for p in providers], **extra}


def ok(content=None, finish='stop'):
    return httpx.Response(200, json={'choices': [{'finish_reason': finish, 'message': {'content': json.dumps(REPLY) if content is None else content}}]})


class FreePoolTests(unittest.IsolatedAsyncioTestCase):
    async def ask(self, pool, handler):
        client_type = httpx.AsyncClient
        def client(*args, **kwargs):
            return client_type(*args, **kwargs, transport=httpx.MockTransport(handler))
        with patch('study_backend.free_apis.httpx.AsyncClient', client):
            return await pool.generate(ChatReply, 'Chào', [])

    async def test_a_rate_limited_member_hands_the_request_to_the_next(self):
        hosts = []
        def handler(request):
            hosts.append(request.url.host)
            self.assertTrue(request.headers['authorization'].startswith('Bearer fixture-'))
            return httpx.Response(429, headers={'retry-after': '30'}) if request.url.host == 'api.groq.com' else ok()
        pool = FreePoolAI(config('groq', 'cerebras'))
        self.assertEqual((await self.ask(pool, handler))['text'], 'Chào bạn')
        self.assertEqual(hosts, ['api.groq.com', 'api.cerebras.ai'])
        self.assertEqual(pool.last_member, 'cerebras/cerebras-model')
        # Groq rests after its 429, so the next request goes straight to Cerebras.
        hosts.clear()
        await self.ask(pool, handler)
        self.assertEqual(hosts, ['api.cerebras.ai'])

    async def test_models_without_json_schema_get_the_schema_in_the_prompt(self):
        formats = []
        def handler(request):
            body = json.loads(request.content)
            formats.append(body.get('response_format', {}).get('type'))
            if formats[-1] == 'json_schema':
                return httpx.Response(400, json={'error': {'message': 'json_schema is not supported'}})
            self.assertIn('đúng schema', body['messages'][-1]['content'])
            return ok('<think>nháp</think>\n```json\n' + json.dumps(REPLY) + '\n```')
        pool = FreePoolAI(config('mistral'))
        self.assertEqual((await self.ask(pool, handler))['text'], 'Chào bạn')
        await self.ask(pool, handler)
        self.assertEqual(formats, ['json_schema', 'json_object', 'json_object'])

    async def test_when_every_member_fails_nothing_is_used_and_the_error_names_them(self):
        def handler(request):
            return ok('không phải JSON') if request.url.host == 'openrouter.ai' else httpx.Response(503)
        with self.assertRaises(ProviderError) as caught:
            await self.ask(FreePoolAI(config('groq', 'openrouter')), handler)
        self.assertEqual(caught.exception.code, 'INVALID_OUTPUT')
        self.assertIn('Groq', str(caught.exception))
        self.assertIn('OpenRouter', str(caught.exception))
        with self.assertRaises(ProviderError) as caught:
            await self.ask(FreePoolAI(config('nvidia')), lambda request: ok(finish='length'))
        self.assertEqual(caught.exception.code, 'INCOMPLETE_OUTPUT')

    def test_json_text_keeps_only_the_object(self):
        self.assertEqual(json.loads(json_text('Kết quả đây: {"a": 1} hết.')), {'a': 1})

    def test_config_is_private_and_https_and_can_be_the_default(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'free.json'
            path.write_text(json.dumps(config('groq', default=True)))
            path.chmod(0o644)
            isolated = {'STUDY_FREE_APIS_CONFIG': str(path), 'STUDY_LOCAL_MODELS': '', 'STUDY_PROVIDER': 'local',
                        'STUDY_KAGGLE_CONFIG': str(Path(tmp) / 'none.json'), 'STUDY_GEMINI_CONFIG': str(Path(tmp) / 'none.json'),
                        'GEMINI_API_KEY': ''}
            with patch.dict(os.environ, isolated):
                with self.assertRaises(ValueError):
                    private_config()
                path.chmod(0o600)
                registry = configured_registry()
                self.assertEqual(registry.default_id, 'free:pool')
                self.assertNotIn('fixture-groq', json.dumps(registry.choices['free:pool'].metadata()))
                path.write_text(json.dumps({'members': [{'provider': 'x', 'api_key': 'k', 'models': ['m'], 'base_url': 'http://evil.example/v1'}]}))
                with self.assertRaises(ValueError):
                    private_config()
