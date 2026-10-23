"""Accounts keep what a browser already learned and open it again from another browser."""
from fastapi.testclient import TestClient
from test_slice import SliceFixture


class AccountTests(SliceFixture):
    def browser(self):
        client = TestClient(self.app, base_url='http://127.0.0.1')
        client.post('/api/session')
        return client

    def style(self, client):
        return client.get('/api/tutor-style').json()['persona']

    def test_registering_keeps_the_anonymous_learners_data_and_login_opens_it_elsewhere(self):
        first = self.browser()
        first.put('/api/tutor-style', json={'persona': 'Mèo mọt sách', 'emphasis': '', 'expected_version': 0}).raise_for_status()
        self.assertFalse(first.get('/api/account').json()['signed_in'])
        made = first.post('/api/account/register', json={'email': 'Huy@Gmail.com', 'password': 'mat-khau-dai', 'name': 'Huy'}).json()
        self.assertEqual((made['signed_in'], made['email'], made['name']), (True, 'huy@gmail.com', 'Huy'))
        self.assertEqual(self.style(first), 'Mèo mọt sách')
        second = self.browser()
        self.assertEqual(second.post('/api/account/login', json={'email': 'huy@gmail.com', 'password': 'sai-mat-khau'}).status_code, 401)
        second.post('/api/account/login', json={'email': 'HUY@gmail.com', 'password': 'mat-khau-dai'}).raise_for_status()
        self.assertEqual(self.style(second), 'Mèo mọt sách')
        self.assertEqual(self.browser().post('/api/account/register', json={'email': 'huy@gmail.com', 'password': 'khac-hoan-toan'}).status_code, 409)
        self.assertEqual(self.browser().post('/api/account/register', json={'email': 'khong-phai-email', 'password': 'mat-khau-dai'}).status_code, 422)
        self.assertEqual(self.browser().post('/api/account/register', json={'email': 'ngan@gmail.com', 'password': 'ngan'}).status_code, 422)
        second.post('/api/account/logout').raise_for_status()
        self.assertEqual(second.get('/api/tutor-style').status_code, 401)
        self.assertTrue(first.get('/api/account').json()['signed_in'])

    def test_repeated_wrong_passwords_are_slowed_down(self):
        self.browser().post('/api/account/register', json={'email': 'a@b.vn', 'password': 'mat-khau-dai'}).raise_for_status()
        client = self.browser()
        codes = [client.post('/api/account/login', json={'email': 'a@b.vn', 'password': 'sai'}).status_code for _ in range(9)]
        self.assertEqual(codes[:8], [401] * 8)
        self.assertEqual(codes[8], 429)
