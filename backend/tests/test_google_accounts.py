"""Sign-in keeps learner data, requires Google's proof, and cannot be replayed."""
import time
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from google.auth import crypt, jwt
from google.auth.exceptions import TransportError
from fastapi.testclient import TestClient

from test_slice import SliceFixture


CLIENT_ID = 'clawledge-test.apps.googleusercontent.com'
VERIFY = 'study_backend.google_accounts.id_token.verify_oauth2_token'


class GoogleAccountTests(SliceFixture):
    def setUp(self):
        self.environment = patch.dict('os.environ', {'STUDY_GOOGLE_CLIENT_ID': CLIENT_ID})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        super().setUp()

    def browser(self):
        client = TestClient(self.app, base_url='http://127.0.0.1')
        client.post('/api/session').raise_for_status()
        return client

    def style(self, client):
        return client.get('/api/tutor-style').json()['persona']

    def claims(self, client, **changes):
        challenge = client.post('/api/account/google/challenge')
        challenge.raise_for_status()
        return {'sub': 'google-person-1', 'email': 'huy@gmail.com', 'email_verified': True,
                'name': 'Huy', 'nonce': challenge.json()['nonce'], **changes}

    def sign_in(self, client, claims):
        with patch(VERIFY, return_value=claims) as verifier:
            response = client.post('/api/account/google', json={'credential': 'test-google-id-token'})
            self.assertEqual(verifier.call_args.kwargs['audience'], CLIENT_ID)
            return response

    def test_config_has_only_the_public_client_id(self):
        self.assertEqual(self.client.get('/api/account/google/config').json(), {'enabled': True, 'client_id': CLIENT_ID})

    def test_google_registration_keeps_data_and_returning_google_opens_it_elsewhere(self):
        first = self.browser()
        old_cookie = first.cookies.get('study_session')
        first.put('/api/tutor-style', json={'persona': 'Giảng chậm, có ví dụ', 'emphasis': '', 'expected_version': 0}).raise_for_status()
        result = self.sign_in(first, self.claims(first))
        result.raise_for_status()
        self.assertTrue(result.json()['google_linked'])
        self.assertEqual(self.style(first), 'Giảng chậm, có ví dụ')
        self.assertNotEqual(first.cookies.get('study_session'), old_cookie)
        old = self.browser()
        old.cookies.set('study_session', old_cookie, domain='127.0.0.1', path='/')
        self.assertEqual(old.get('/api/tutor-style').status_code, 401)
        second = self.browser()
        self.sign_in(second, self.claims(second)).raise_for_status()
        self.assertEqual(self.style(second), 'Giảng chậm, có ví dụ')
        self.assertEqual(second.get('/api/account').json()['email'], 'huy@gmail.com')

    def test_nonce_is_bound_to_the_browser_expires_and_is_one_use(self):
        first, other = self.browser(), self.browser()
        proof = self.claims(first)
        self.assertEqual(self.sign_in(other, proof).status_code, 401)
        self.sign_in(first, proof).raise_for_status()
        self.assertEqual(self.sign_in(first, proof).status_code, 401)
        expired = self.claims(other)
        with self.app.state.database.connection(write=True) as db:
            db.execute('UPDATE google_login_challenges SET expires_at=0')
        self.assertEqual(self.sign_in(other, expired).status_code, 401)

    def test_existing_password_account_must_sign_in_before_connecting_google(self):
        owner = self.browser()
        owner.post('/api/account/register', json={'email': 'huy@gmail.com', 'password': 'mat-khau-dai'}).raise_for_status()
        stranger = self.browser()
        self.assertEqual(self.sign_in(stranger, self.claims(stranger)).status_code, 409)
        wrong = self.claims(owner, email='someone@gmail.com')
        self.assertEqual(self.sign_in(owner, wrong).status_code, 409)
        self.sign_in(owner, self.claims(owner)).raise_for_status()
        self.assertTrue(owner.get('/api/account').json()['google_linked'])
        self.sign_in(stranger, self.claims(stranger)).raise_for_status()
        self.assertEqual(stranger.get('/api/account').json()['email'], 'huy@gmail.com')

    def test_invalid_claims_never_create_an_account(self):
        client = self.browser()
        for changes in [{'email_verified': False}, {'nonce': ''}, {'sub': ''}, {'azp': 'another-app'}, {'email': 'not-email'}]:
            self.assertEqual(self.sign_in(client, self.claims(client, **changes)).status_code, 401)
            self.assertFalse(client.get('/api/account').json()['signed_in'])
        with patch(VERIFY, side_effect=TransportError('offline')):
            self.assertEqual(client.post('/api/account/google', json={'credential': 'test-google-id-token'}).status_code, 503)

    def test_google_library_rejects_bad_audience_signature_and_expired_tokens(self):
        # Exercise the real verifier using a local signing key and local public cert;
        # only Google's certificate download is substituted, so there are no external calls.
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        signer = crypt.RSASigner.from_string(private, key_id='test-key')
        client = self.browser()
        claims = {**self.claims(client), 'aud': CLIENT_ID, 'iss': 'https://accounts.google.com', 'iat': int(time.time()) - 10, 'exp': int(time.time()) + 600}
        with patch('google.oauth2.id_token._fetch_certs', return_value={'test-key': public}):
            for changes in [{'aud': 'wrong-app'}, {'exp': int(time.time()) - 60}, {'iss': 'https://wrong-issuer.example'}]:
                token = jwt.encode(signer, {**claims, **changes}).decode()
                self.assertEqual(client.post('/api/account/google', json={'credential': token}).status_code, 401)
            token = jwt.encode(signer, claims).decode()
            parts = token.split('.')
            parts[2] = ('B' if parts[2][0] != 'B' else 'C') + parts[2][1:]
            self.assertEqual(client.post('/api/account/google', json={'credential': '.'.join(parts)}).status_code, 401)
            client.post('/api/account/google', json={'credential': token}).raise_for_status()

    def test_cross_origin_is_rejected_before_verifying_any_token(self):
        client = self.browser()
        with patch(VERIFY) as verifier:
            response = client.post('/api/account/google', json={'credential': 'test-google-id-token'}, headers={'Origin': 'https://other.example'})
        self.assertEqual(response.status_code, 403)
        verifier.assert_not_called()


class GoogleDisabledTests(SliceFixture):
    def setUp(self):
        self.environment = patch.dict('os.environ', {'STUDY_GOOGLE_CLIENT_ID': ''})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        super().setUp()

    def test_unconfigured_google_does_not_break_password_login(self):
        self.assertEqual(self.client.get('/api/account/google/config').json(), {'enabled': False, 'client_id': None})
        self.assertEqual(self.client.post('/api/account/google/challenge').status_code, 503)
        self.assertEqual(self.client.post('/api/account/google', json={'credential': 'test-google-id-token'}).status_code, 503)
