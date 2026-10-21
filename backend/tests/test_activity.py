from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from test_slice import SliceFixture


class ActivityTests(SliceFixture):
    def setUp(self):
        super().setUp()
        self.course_value = self.course()
        self.owner = self.client.post('/api/session').json()['id']
        self.clock = datetime(2026, 10, 15, 18, tzinfo=timezone.utc)
        self.app.state.economy.clock = lambda: self.clock
        self.app.state.economy.enabled = True
        self.path = '/api/courses/' + self.course_value['id']

    def complete_round(self):
        session = self.client.post(self.path + '/sessions', json={'expected_revision': 2, 'unit_id': 'unit-1'}).json()
        for q in session['questions']:
            answer = {'mcq': 'option-1', 'cloze': '0', 'matching': {'left-0': 'option-1', 'left-1': 'option-0'},
                      'ordering': ['option-1', 'option-0'], 'short_answer': 'My reasoning'}[q['kind']]
            self.client.post(f"/api/sessions/{session['id']}/answers", json={'item_id': q['id'], 'answer': answer}).raise_for_status()
        result = self.client.post(f"/api/sessions/{session['id']}/complete");result.raise_for_status()
        return session, result.json()

    def test_empty_dashboard_partial_round_no_activity_and_zero_score_unlock_does_not_require_missions(self):
        dashboard = self.client.get('/api/dashboard?year=2026').json()
        self.assertEqual(len(dashboard['timeline']), 365)
        self.assertTrue(all(d['rounds'] == d['seconds'] == 0 for d in dashboard['timeline']))
        self.assertEqual(dashboard['weekly_streak']['current'], 0)
        pending = self.client.post(self.path + '/sessions', json={'expected_revision': 2, 'unit_id': 'unit-1'}).json()
        self.assertEqual(self.client.post(f"/api/sessions/{pending['id']}/complete").status_code, 409)
        self.assertEqual(self.client.get('/api/dashboard').json()['weekly_streak']['current'], 0)
        session, result = self.complete_round()
        self.assertEqual(result['score'], 0)
        course = self.client.get(self.path).json()
        self.assertTrue(course['content']['units'][1]['unlocked'])
        self.assertEqual(self.client.get('/api/dashboard').json()['learning_progress'][0]['percent'], 50)
        self.assertFalse(self.client.get('/api/missions').json()['missions_gate_lessons'])
        initial = self.client.get('/api/wallet').json()['balance']
        self.assertEqual(initial, 24)
        self.assertEqual(self.client.post(f"/api/sessions/{session['id']}/complete").json(), result)
        self.complete_round()  # A new session using the same bank gives no new reward today.
        self.assertEqual(self.client.get('/api/wallet').json()['balance'], initial)
        achieved = self.client.get('/api/achievements').json()['earned']
        self.assertEqual([a['code'] for a in achieved], ['first_session'])

    def test_local_day_streak_real_dates_and_utc_reward_day_are_separate(self):
        self.complete_round()
        for _ in range(2):
            self.clock += timedelta(days=1)
            self.complete_round()
        data = self.client.get('/api/dashboard?year=2026').json()
        self.assertEqual(data['weekly_streak']['current'], 3)
        dates = [d['date'] for d in data['timeline'] if d['qualified']]
        self.assertEqual(dates, ['2026-10-16', '2026-10-17', '2026-10-18'])
        self.assertIn('study_day_3', [a['code'] for a in self.client.get('/api/achievements').json()['earned']])
        self.assertEqual(self.client.get('/api/wallet').json()['balance'], 30)
        self.assertEqual(self.client.get('/api/missions').json()['utc_day'], '2026-10-17')
        self.client.put('/api/activity/profile', json={'timezone': 'America/Los_Angeles'}).raise_for_status()
        changed = self.client.get('/api/dashboard').json()
        self.assertEqual(changed['weekly_streak']['current'], 3)
        self.assertEqual([d['date'] for d in changed['timeline'] if d['qualified']], ['2026-10-15', '2026-10-16', '2026-10-17'])
        self.assertEqual(self.client.get('/api/wallet').json()['balance'], 30)
        self.clock += timedelta(days=2)
        self.assertEqual(self.client.get('/api/dashboard').json()['weekly_streak']['current'], 0)
        self.assertEqual(self.client.get('/api/dashboard').json()['weekly_streak']['longest'], 3)

    def test_five_distinct_cards_qualify_even_not_remembered_toggle_cannot_farm_and_zero_coin_still_works(self):
        calls_before_review=self.provider.calls
        self.client.get('/api/wallet')
        with self.app.state.database.connection(write=True) as db:
            db.execute('UPDATE wallets SET balance=0 WHERE owner_id=?', (self.owner,))
        cards = self.client.get('/api/cards?course_id=' + self.course_value['id']).json()
        for i in range(4):
            created = self.client.post('/api/cards', json={'front': f'Term {i}', 'back': f'Meaning {i}', 'course_id': self.course_value['id']})
            created.raise_for_status();cards.append(created.json())
        first = cards[0]
        for version in range(6):
            self.client.put('/api/cards/' + first['id'] + '/memory', json={'course_id': self.course_value['id'], 'remembered': bool(version % 2), 'expected_version': version}).raise_for_status()
        self.assertEqual(self.client.get('/api/dashboard').json()['weekly_streak']['current'], 0)
        self.assertEqual(self.client.get('/api/wallet').json()['balance'], 0)
        for card in cards[1:]:
            self.client.put('/api/cards/' + card['id'] + '/memory', json={'course_id': self.course_value['id'], 'remembered': False, 'expected_version': 0}).raise_for_status()
        self.assertEqual(self.client.get('/api/dashboard').json()['weekly_streak']['current'], 1)
        self.assertEqual(self.client.get('/api/wallet').json()['balance'], 2)
        self.assertTrue(next(m for m in self.client.get('/api/missions').json()['daily'] if m['code'] == 'cards')['completed'])
        self.assertEqual(self.provider.calls, calls_before_review)  # No AI calls for review or rewards.

    def test_heartbeat_is_bounded_no_idle_credit_no_double_tab_or_replay_and_no_study_day(self):
        body = {'course_id': self.course_value['id'], 'unit_id': 'unit-1', 'expected_revision': 2, 'mode': 'learn'}
        first = self.client.post('/api/activity/ping', json=body).json()
        self.assertEqual(first['credited_seconds'], 0)
        self.clock += timedelta(seconds=20)
        pulse = {**body, 'lease_id': first['lease_id'], 'expected_sequence': 0}
        tick = self.client.post('/api/activity/ping', json=pulse).json()
        self.assertEqual(tick['credited_seconds'], 20)
        self.assertEqual(self.client.post('/api/activity/ping', json=pulse).status_code, 409)
        other_tab = self.client.post('/api/activity/ping', json=body).json()
        self.assertEqual(self.client.post('/api/activity/ping', json={**pulse, 'expected_sequence': 1}).status_code, 409)
        self.clock += timedelta(seconds=20)
        tick = self.client.post('/api/activity/ping', json={**body, 'lease_id': other_tab['lease_id'], 'expected_sequence': 0}).json()
        self.assertEqual(tick['credited_seconds'], 20)
        self.clock += timedelta(hours=1)
        late = self.client.post('/api/activity/ping', json={**body, 'lease_id': tick['lease_id'], 'expected_sequence': 1}).json()
        self.assertEqual(late['credited_seconds'], 0)
        data = self.client.get('/api/dashboard').json()
        self.assertEqual(sum(d['seconds'] for d in data['timeline']), 40)
        self.assertEqual(data['weekly_streak']['current'], 0)
        self.assertEqual(self.client.put('/api/activity/profile', json={'timezone': 'invalid/zone'}).status_code, 422)
        with TestClient(self.app, base_url='http://127.0.0.1') as peer:
            peer.post('/api/session')
            self.assertEqual(peer.post('/api/activity/ping', json=body).status_code, 404)
            self.assertEqual(peer.get('/api/achievements').json()['earned'], [])
            self.assertEqual(sum(d['seconds'] for d in peer.get('/api/dashboard').json()['timeline']), 0)

    def test_leap_year_and_weak_mission_requires_real_wrong_history(self):
        self.assertEqual(len(self.client.get('/api/dashboard?year=2024').json()['timeline']), 366)
        weak = next(m for m in self.client.get('/api/missions').json()['daily'] if m['code'] == 'weak')
        self.assertTrue(weak['suggest_initial_practice'])
        self.assertEqual(self.client.post(self.path + '/sessions', json={'expected_revision': 2, 'unit_id': 'unit-1', 'exercise': 'weak'}).status_code, 409)
        self.assertFalse(weak['completed'])
