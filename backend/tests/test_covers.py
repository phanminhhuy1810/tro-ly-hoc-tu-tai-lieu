"""Course covers: drawn presets or a small uploaded image, set by the creator only."""
from fastapi.testclient import TestClient
from test_slice import SliceFixture

PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 64


class CoverTests(SliceFixture):
    def setUp(self):
        super().setUp()
        self.value = self.course()
        self.base = '/api/courses/' + self.value['id']

    def test_preset_then_upload_then_reset(self):
        self.assertEqual(self.client.get('/api/covers').json(), {})
        self.assertEqual(self.client.put(self.base + '/cover', json={'preset': '../etc-sage'}).status_code, 422)
        self.assertEqual(self.client.put(self.base + '/cover', json={'preset': 'rocket-purple'}).status_code, 422)
        self.assertEqual(self.client.put(self.base + '/cover', json={'preset': 'rocket-lilac'}).json()['preset'], 'rocket-lilac')
        chosen = self.client.put(self.base + '/cover', json={'preset': 'network-sky'}).json()
        self.assertEqual((chosen['kind'], chosen['preset']), ('preset', 'network-sky'))
        self.assertEqual(self.client.get('/api/covers').json()[self.value['id']]['preset'], 'network-sky')
        self.assertEqual(self.client.get(self.base + '/cover/image').status_code, 404)
        uploaded = self.client.post(self.base + '/cover/upload', files={'file': ('cover.png', PNG, 'image/png')}).json()
        self.assertEqual(uploaded['kind'], 'upload')
        image = self.client.get(self.base + '/cover/image')
        self.assertEqual((image.content, image.headers['content-type']), (PNG, 'image/png'))
        self.assertEqual(self.client.delete(self.base + '/cover').json(), {'kind': 'auto'})
        self.assertEqual(self.client.get('/api/covers').json(), {})

    def test_only_images_within_the_limit_and_only_the_creator(self):
        self.assertEqual(self.client.post(self.base + '/cover/upload', files={'file': ('x.png', b'<svg onload=alert(1)>', 'image/png')}).status_code, 415)
        self.assertEqual(self.client.post(self.base + '/cover/upload', files={'file': ('big.png', PNG + b'\x00' * 1_600_000, 'image/png')}).status_code, 413)
        with TestClient(self.app, base_url='http://127.0.0.1') as stranger:
            stranger.post('/api/session')
            self.assertIn(stranger.put(self.base + '/cover', json={'preset': 'network-sky'}).status_code, {403, 404})
            self.assertIn(stranger.get(self.base + '/cover/image').status_code, {403, 404})
