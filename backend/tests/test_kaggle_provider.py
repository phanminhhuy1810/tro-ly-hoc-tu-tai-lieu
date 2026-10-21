"""Provider configuration and transport boundaries; no live GPU in unit tests."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from study_backend.ai import KaggleAI, LocalAI, configured_ai
from study_backend.models import ChatReply


CONFIG = {"endpoint": "https://study-test.ngrok-free.dev", "model": "qwen3.8:27b",
          "username": "study", "password": "test-password-only-never-a-real-secret"}


class ConfigurationTests(unittest.TestCase):
    def test_remote_requires_secure_explicit_endpoint_and_auth(self):
        for url in ["http://study-test.ngrok-free.dev", "https://localhost", "https://ngrok-free.dev",
                    "https://evil.test", "https://x.ngrok-free.dev.evil.test", "https://u:p@x.ngrok.app",
                    "https://x.ngrok.app/api", "https://x.ngrok.app?secret=x", "https://x.ngrok.app:444"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                KaggleAI({**CONFIG, "endpoint": url})
        with self.assertRaises(ValueError):
            KaggleAI({**CONFIG, "password": ""})

    def test_local_remains_default_and_unknown_provider_fails_closed(self):
        with patch.dict(os.environ, {"STUDY_PROVIDER": "local"}):
            self.assertEqual(configured_ai().endpoint, "http://127.0.0.1:11434")
        with patch.dict(os.environ, {"STUDY_PROVIDER": "typo"}), self.assertRaises(ValueError):
            configured_ai()

    def test_private_config_permissions_and_metadata(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "private.json"
            path.write_text(json.dumps(CONFIG)); path.chmod(0o644)
            with patch.dict(os.environ, {"STUDY_PROVIDER": "kaggle", "STUDY_KAGGLE_CONFIG": str(path)}):
                with self.assertRaises(ValueError): configured_ai()
                path.chmod(0o600)
                ai = configured_ai()
                self.assertEqual(ai.metadata()["provider"], "ollama_kaggle")
                self.assertNotIn(CONFIG["password"], json.dumps(ai.metadata()))
                self.assertNotIn(CONFIG["endpoint"], json.dumps(ai.metadata()))


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, handler, action):
        client_type = httpx.AsyncClient
        def client(*args, **kwargs):
            return client_type(*args, **kwargs, transport=httpx.MockTransport(handler))
        with patch("study_backend.ai.httpx.AsyncClient", client):
            return await action(KaggleAI(CONFIG))

    async def test_auth_is_server_side_and_not_returned_in_status(self):
        seen = []
        def handler(request):
            seen.append(request)
            return httpx.Response(200, json={"models": [{"name": CONFIG["model"]}]})
        result = await self.exercise(handler, lambda ai: ai.status())
        self.assertTrue(result["ready"])
        self.assertTrue(seen[0].headers["authorization"].startswith("Basic "))
        self.assertNotIn("password", json.dumps(result))
        async with LocalAI().client(5) as client:
            self.assertNotIn("authorization", client.headers)

    async def test_remote_redirect_or_auth_failure_does_not_fallback(self):
        for status in [302, 401, 503]:
            calls = []
            def handler(request):
                calls.append(str(request.url))
                return httpx.Response(status, headers={"location": "https://evil.test/"}, json={})
            result = await self.exercise(handler, lambda ai: ai.status())
            self.assertFalse(result["ready"])
            self.assertEqual(len(calls), 1)
            self.assertTrue(calls[0].startswith(CONFIG["endpoint"]))

    async def test_generated_reply_still_requires_valid_source_refs(self):
        def handler(request):
            if request.url.path == "/api/tags":
                return httpx.Response(200, json={"models": [{"name": CONFIG["model"]}]})
            payload = json.loads(request.content)
            self.assertFalse(payload["think"])
            self.assertEqual(payload["model"], CONFIG["model"])
            return httpx.Response(200, json={"done_reason": "stop", "message": {"content": json.dumps({
                "text": "Unsupported reference", "source_refs": ["outside"], "needs_more_source": False})}})
        with self.assertRaises(ValueError):
            await self.exercise(handler, lambda ai: ai.generate(ChatReply, "Explain", [{"id": "f1", "text": "IPv4"}]))
