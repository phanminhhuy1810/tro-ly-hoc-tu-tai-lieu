"""Input behaviour/authorization tests. Native OCR is measured separately."""
import asyncio
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import httpx
from study_backend.app import create_app
from study_backend.extract import extract
from study_backend.public_urls import fetch_article, public_target, parse_article, send, MAX_URL_BYTES
from test_slice import TestProvider


class URLTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_dns_answers_must_be_public(self):
        for addresses in [["127.0.0.1"], ["169.254.169.254"], ["10.0.0.1"], ["::1"], ["::ffff:127.0.0.1"], ["64:ff9b::7f00:1"], ["8.8.8.8", "192.168.0.1"]]:
            async def resolver(host, port): return addresses
            with self.subTest(addresses=addresses), self.assertRaises(ValueError):
                await public_target("https://example.com/article", resolver)
        for url in ["file:///etc/passwd", "https://user:pass@example.com", "http://example.com:11434", "https://example.com/\n"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                await public_target(url)

    async def test_redirect_revalidates_target_before_sending(self):
        sends = []
        async def resolver(host, port): return ["127.0.0.1" if host == "private.test" else "8.8.8.8"]
        async def sender(url, host, ip):
            sends.append((url, host, ip))
            return 302, {"location": "http://private.test/secret"}, b""
        with self.assertRaises(ValueError):
            await fetch_article("https://public.test/article", resolver, sender)
        self.assertEqual(len(sends), 1)
        self.assertEqual(sends[0][2], "8.8.8.8")

    async def test_pinned_transport_keeps_host_tls_and_sends_no_auth_or_cookie(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, headers={"Content-Type": "text/plain"}, content=b"public text")
        client_type = httpx.AsyncClient
        def factory(*args, **kwargs): return client_type(*args, **kwargs, transport=httpx.MockTransport(handler))
        with patch("study_backend.public_urls.httpx.AsyncClient", factory):
            status, _, body = await send("https://public.test/a", "public.test", "8.8.8.8")
        self.assertEqual((status, body), (200, b"public text"))
        request = requests[0]
        self.assertEqual(request.url.host, "8.8.8.8")
        self.assertEqual(request.headers["host"], "public.test")
        self.assertEqual(request.extensions["sni_hostname"], "public.test")
        self.assertNotIn("authorization", request.headers)
        self.assertNotIn("cookie", request.headers)

    async def test_redirect_limit_large_nonarticle_and_login_rejected(self):
        async def resolver(host, port): return ["8.8.8.8"]
        cases = [(302, {"location": "/next"}, b""),
                 (200, {"content-type": "application/pdf"}, b"%PDF"),
                 (200, {"content-type": "text/plain"}, b"x" * (MAX_URL_BYTES+1)),
                 (200, {"content-type": "text/html"}, b'<form><input type="password"></form>'),
                 (403, {"content-type": "text/html"}, b"no")]
        for result in cases:
            async def sender(url, host, ip): return result
            with self.subTest(status=result[0], type=result[1]), self.assertRaises(ValueError):
                await fetch_article("https://public.test/a", resolver, sender)

    async def test_article_preserves_inline_text_math_headings_and_snapshot(self):
        raw = b'<title>Study</title><nav>IGNORE</nav><article><h1 id="topic">Subnet</h1><p>An <b>IPv4</b> address.</p><p><script type="math/tex">2^{6}-2=62</script> hosts.</p><script>IGNORE</script></article>'
        async def resolver(host, port): return ["8.8.8.8"]
        async def sender(url, host, ip): return 200, {"content-type": "text/html"}, raw
        article = await fetch_article("https://public.test/a#fragment", resolver, sender)
        self.assertEqual(article["original"], raw)
        self.assertEqual(article["url"], "https://public.test/a")
        self.assertIn("An IPv4 address.", article["text"])
        self.assertIn(r"\(2^{6}-2=62\)", article["text"])
        self.assertNotIn("IGNORE", article["text"])
        self.assertEqual(article["fragments"][1]["locator"]["heading"], "Subnet")
        self.assertEqual(article["fragments"][1]["locator"]["paragraph"], 2)


class InputAPI(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        root = Path(self.temp.name)
        async def article(url):
            raw = b'<article><h1>Subnet</h1><p>32 bits.</p></article>'
            return {"url": "https://public.test/article", "content_type": "text/html", "original": raw,
                    **parse_article(raw, "text/html", "https://public.test/article", "public.test")}
        self.app = create_app(root/"data.sqlite", root/"sources", TestProvider(), extractor=lambda name, data: extract(name, data, ocr=False), article_fetcher=article, economy_enabled=False)
        self.client = TestClient(self.app, base_url="http://127.0.0.1")
        self.client.post('/api/session').raise_for_status()

    def tearDown(self):
        self.client.close(); self.temp.cleanup()

    def test_failed_read_keeps_original_and_manual_recovery_requires_review(self):
        raw = b"invalid image bytes"
        response = self.client.post('/api/sources/upload', files={"file": ("scan.png", raw, "image/png")})
        self.assertEqual(response.status_code, 422)
        detail = response.json()["detail"]
        self.assertTrue(detail["original_retained"])
        source_id = detail["source_id"]
        path = '/api/sources/' + source_id
        source = self.client.get(path).json()
        self.assertEqual((source["status"], source["revision"], source["fragments"]), ("failed", 0, []))
        self.assertEqual(self.client.get(path+'/original').content, raw)
        self.assertEqual(self.client.post(path+'/retry-extraction', json={"expected_revision": 0}).status_code, 422)
        recovered = self.client.post(path+'/transcription', json={"expected_revision": 0, "text": "32 bits.\nHost count = 62."}).json()
        self.assertEqual((recovered["revision"], recovered["reviewed"]), (1, False))
        self.assertTrue(recovered["fragments"][0]["locator"]["location_unverified"])
        self.assertEqual(self.client.post(path+'/transcription', json={"expected_revision": 0, "text": "stale"}).status_code, 409)
        confirmed = self.client.post(path+'/review', json={"expected_revision": 1, "texts": [f["text"] for f in recovered["fragments"]]}).json()
        self.assertTrue(confirmed["reviewed"])
        self.assertEqual(self.client.get(path+'/original').content, raw)
        foreign = TestClient(self.app, base_url="http://127.0.0.1")
        foreign.post('/api/session')
        self.assertEqual(foreign.post(path+'/transcription', json={"expected_revision": 2, "text": "steal"}).status_code, 404)
        foreign.close()

    def test_article_snapshot_locator_review_and_retry_do_not_fetch_again(self):
        source = self.client.post('/api/sources/url', json={"url": "https://public.test/article"}).json()
        path = '/api/sources/' + source['id']
        raw = self.client.get(path+'/original').content
        self.assertEqual(source["metadata"]["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(source["fragments"][1]["locator"]["heading"], "Subnet")
        self.assertFalse(source["reviewed"])
        confirmed = self.client.post(path+'/review', json={"expected_revision": 1, "texts": [f["text"] for f in source["fragments"]]}).json()
        retried = self.client.post(path+'/retry-extraction', json={"expected_revision": 2}).json()
        self.assertEqual((retried["revision"], retried["reviewed"]), (3, False))
        self.assertEqual(self.client.get(path+'?revision=2').json(), {**confirmed, "status": "needs_review", "metadata": retried["metadata"]})
        self.assertEqual(self.client.get(path+'/original').content, raw)

    def test_vision_preview_apply_is_page_scoped_revision_checked_and_private(self):
        class VisionProvider(TestProvider):
            async def transcribe_image(self, image):
                self.calls += 1
                return {"text": r"\int_0^1 x^2 dx = \frac{1}{3}", "uncertain_spans": [], "model": "test_vision"}
        root = Path(self.temp.name)/'vision'
        raw = b"test PDF fixture; renderer/reader are explicitly test doubles"
        def reader(name, data):
            return ([{"text": "wrong formula", "locator": {"page": 1}}, {"text": "keep page two", "locator": {"page": 2}}], [])
        provider = VisionProvider()
        app = create_app(root/'data.sqlite', root/'sources', provider, extractor=reader, page_renderer=lambda name, data, page: (b'fixture png', {"width": 50, "height": 50}), economy_enabled=False)
        client = TestClient(app, base_url='http://127.0.0.1'); client.post('/api/session')
        source = client.post('/api/sources/upload', files={'file': ('scan.pdf', raw, 'application/pdf')}).json()
        path = '/api/sources/'+source['id']
        response = client.post(path+'/vision-review', json={"expected_revision": 1, "page": 1}, headers={'Idempotency-Key':'vision-one'})
        job = client.get('/api/jobs/'+response.json()['job_id']).json()
        self.assertEqual(job['status'], 'succeeded', job)
        proposal_path = '/api/source-proposals/'+job['result']['source_proposal_id']
        proposal = client.get(proposal_path).json()
        self.assertEqual(len(proposal['before']), 1)
        self.assertEqual(client.get(path).json()['fragments'], source['fragments'])
        repeat = client.post(path+'/vision-review', json={"expected_revision": 1, "page": 1}, headers={'Idempotency-Key':'vision-one'})
        self.assertEqual(repeat.json(), response.json()); self.assertEqual(provider.calls, 1)
        foreign = TestClient(app, base_url='http://127.0.0.1'); foreign.post('/api/session')
        self.assertEqual(foreign.get(proposal_path).status_code, 404)
        self.assertEqual(foreign.post(proposal_path+'/apply', json={'expected_revision':1}).status_code, 404)
        self.assertEqual(client.post(proposal_path+'/apply', json={'expected_revision':0}).status_code, 409)
        applied = client.post(proposal_path+'/apply', json={'expected_revision':1}).json()
        self.assertEqual((applied['revision'], applied['reviewed']), (2, False))
        self.assertEqual(applied['fragments'][1]['text'], 'keep page two')
        self.assertEqual(applied['fragments'][0]['provenance']['kind'], 'ai_transcription')
        self.assertEqual(client.get(path+'/original').content, raw)
        self.assertEqual(client.post(proposal_path+'/apply', json={'expected_revision':1}).json(), applied)
        self.assertEqual(client.post(proposal_path+'/discard').status_code, 409)
        foreign.close(); client.close()
