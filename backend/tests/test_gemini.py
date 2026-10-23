"""Transport contracts use explicit fixtures, never the machine's real API key."""
import asyncio
import json
import unittest
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx

from study_backend.gemini import GeminiAI, ProviderError
from study_backend.models import ChatReply, QUESTION_DRAFTS


class GeminiTests(unittest.IsolatedAsyncioTestCase):
    def adapter(self, enabled=True):
        return GeminiAI('gemini-2.5-flash', api_key='fixture-key-not-real', enabled=enabled)

    async def exercise(self, handler, call):
        client_type = httpx.AsyncClient
        def client(*args, **kwargs):
            return client_type(*args, **kwargs, transport=httpx.MockTransport(handler))
        with patch('study_backend.gemini.httpx.AsyncClient', client):
            return await call()

    def response(self, value, finish='STOP', **extra):
        return httpx.Response(200, json={'candidates': [{'finishReason': finish,
            'content': {'parts': [{'text': json.dumps(value)}]}}], **extra})

    async def test_disabled_config_cannot_call_network_or_generate(self):
        def unexpected(request):
            self.fail('Disabled Gemini attempted a network request')
        ai = self.adapter(False)
        async def action():
            self.assertFalse((await ai.status())['ready'])
            with self.assertRaises(ProviderError) as caught:
                await ai.generate(ChatReply, 'Explain', [])
            self.assertEqual(caught.exception.code, 'PROVIDER_DISABLED')
        await self.exercise(unexpected, action)

    def test_private_config_is_protected_and_never_falls_back_to_another_key(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'gemini.json'; path.write_text(json.dumps({'enabled': True})); path.chmod(0o600)
            with patch.dict(os.environ, {'STUDY_GEMINI_CONFIG': str(path), 'GEMINI_API_KEY': 'different-project-key'}):
                with self.assertRaises(ValueError): GeminiAI()
                path.write_text(json.dumps({'api_key': 'private-fixture-key', 'enabled': False}));path.chmod(0o644)
                with self.assertRaises(ValueError): GeminiAI()
                path.chmod(0o600)
                ai = GeminiAI()
                self.assertFalse(ai.enabled)
                self.assertNotIn('private-fixture-key', json.dumps(ai.metadata()))

    async def test_header_only_key_json_schema_and_source_validation(self):
        requests = []
        def handler(request):
            requests.append(request)
            self.assertEqual(request.headers['x-goog-api-key'], 'fixture-key-not-real')
            self.assertNotIn('key=', str(request.url))
            value = json.loads(request.content)
            self.assertEqual(value['generationConfig']['responseMimeType'], 'application/json')
            self.assertEqual(value['generationConfig']['responseJsonSchema']['type'], 'object')
            self.assertNotIn('tools', value)
            return self.response({'text': 'IPv4 has 32 bits.', 'source_refs': ['f1'], 'needs_more_source': False})
        ai = self.adapter()
        value = await self.exercise(handler, lambda: ai.generate(ChatReply, 'Explain', [{'id': 'f1', 'text': 'IPv4 has 32 bits.'}]))
        self.assertEqual(value['source_refs'], ['f1'])
        self.assertEqual(len(requests), 1)
        self.assertNotIn('fixture-key', json.dumps(ai.metadata()))

    async def test_chat_may_converse_while_generation_stays_source_only(self):
        sent = []
        def handler(request):
            sent.append(json.loads(request.content))
            if 'uncertain_spans' in json.dumps(sent[-1]['generationConfig']['responseJsonSchema']):
                return self.response({'text': 'IPv4 has 32 bits.', 'uncertain_spans': []})
            return self.response({'text': 'Mình là Byte.', 'source_refs': [], 'needs_more_source': False})
        ai = self.adapter()
        await self.exercise(handler, lambda: ai.generate(ChatReply, 'bạn là ai', []))
        await self.exercise(handler, lambda: ai.transcribe_image(b'fixture-image'))
        chat, vision = (value['systemInstruction']['parts'][0]['text'] for value in sent)
        self.assertIn('Byte', chat)
        self.assertNotIn('Chỉ dùng nguồn', chat)
        self.assertIn('Chỉ dùng nguồn', vision)
        self.assertGreater(sent[0]['generationConfig']['temperature'], sent[1]['generationConfig']['temperature'])

    async def test_quota_auth_error_timeout_and_redirect_never_retry_or_echo_body(self):
        for status in [400, 401, 403, 404, 429, 500, 302]:
            calls = []
            def handler(request):
                calls.append(request)
                return httpx.Response(status, json={'error': {'message': 'fixture-key-not-real'}}, headers={'location': 'https://evil.test/'})
            with self.subTest(status=status), self.assertRaises(ProviderError) as caught:
                await self.exercise(handler, lambda: self.adapter().generate(ChatReply, 'Explain', []))
            self.assertEqual(len(calls), 1)
            self.assertNotIn('fixture-key', str(caught.exception))
        def timeout(request): raise httpx.ReadTimeout('fixture-key-not-real')
        with self.assertRaises(ProviderError) as caught:
            await self.exercise(timeout, lambda: self.adapter().generate(ChatReply, 'Explain', []))
        self.assertEqual(caught.exception.code, 'PROVIDER_TIMEOUT')

    async def test_truncated_safety_empty_invalid_or_foreign_source_output_is_not_accepted(self):
        valid = {'text': 'A source answer', 'source_refs': ['f1'], 'needs_more_source': False}
        cases = [self.response(valid, 'MAX_TOKENS'), self.response(valid, 'SAFETY'),
                 httpx.Response(200, json={'promptFeedback': {'blockReason': 'SAFETY'}}),
                 httpx.Response(200, json={'candidates': []}), self.response({'text': 'Missing fields'}),
                 self.response({**valid, 'source_refs': ['other-user-source']})]
        for response in cases:
            with self.subTest(response=response.text), self.assertRaises((ProviderError, ValueError)):
                await self.exercise(lambda request: response, lambda: self.adapter().generate(ChatReply, 'Explain', [{'id': 'f1', 'text': 'Source'}]))

    async def test_vision_returns_a_review_proposal_never_an_automatic_source_change(self):
        def handler(request):
            parts = json.loads(request.content)['contents'][0]['parts']
            self.assertEqual(parts[1]['inlineData']['mimeType'], 'image/png')
            return self.response({'text': 'x^2', 'uncertain_spans': ['power uncertain']})
        result = await self.exercise(handler, lambda: self.adapter().transcribe_image(b'fixture-png'))
        self.assertEqual(result['validation'], 'requires_source_review')
        self.assertEqual(result['uncertain_spans'], ['power uncertain'])

    async def test_question_generation_does_not_ask_ai_to_invent_server_difficulty_metadata(self):
        def handler(request):
            # The old wire contract exposed server provenance to the model; a
            # plausible invented label then rejected an otherwise usable MCQ.
            schema = json.loads(request.content)['generationConfig']['responseJsonSchema']
            question_schema = next(v for v in schema['$defs'].values() if 'prompt' in v.get('properties', {}))
            self.assertNotIn('left', question_schema['properties'])
            self.assertNotIn('rubric', question_schema['properties'])
            question = {'kind': 'mcq', 'prompt': 'How many bits does IPv6 use?', 'options': ['128 bits', '32 bits'],
                        'answer': '128 bits', 'explanation': 'The source states 128 bits.', 'source_refs': ['f1']}
            if 'difficulty_basis' in question_schema['properties']:
                question.update(difficulty='basic', difficulty_basis='known_from_source')
            return self.response({'question': question, 'reason': ''})
        result = await self.exercise(handler, lambda: self.adapter().generate(QUESTION_DRAFTS['mcq'], 'One MCQ', [{'id': 'f1', 'text': 'IPv6 uses 128 bits.'}]))
        self.assertEqual(result['question']['answer'], '128 bits')
        self.assertNotIn('difficulty_basis', result['question'])
