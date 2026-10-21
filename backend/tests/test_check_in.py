from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from tempfile import TemporaryDirectory
from pathlib import Path
import unittest
from fastapi.testclient import TestClient
from study_backend.app import create_app
from test_slice import TestProvider

class CheckInTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.provider=TestProvider();self.clock=datetime(2026,10,18,16,59,tzinfo=timezone.utc)
        root=Path(self.tmp.name);self.app=create_app(root/'db.sqlite',root/'sources',self.provider,clock=lambda:self.clock)
        self.client=TestClient(self.app,base_url='http://127.0.0.1');self.owner=self.client.post('/api/session').json()['id'];self.path='/api/activity/check-in'
    def tearDown(self):self.client.close();self.tmp.cleanup()
    def submit(self):
        r=self.client.post(self.path,json={});r.raise_for_status();return r.json()
    def test_explicit_check_in_once_saved_across_reload_without_coin_ai_or_study_credit(self):
        self.assertFalse(self.client.get(self.path).json()['checked_today']);wallet=self.client.get('/api/wallet').json()
        first=self.submit();self.assertTrue(first['newly_checked']);self.assertEqual(first['today'],'2026-10-18');self.assertEqual(first['current_streak'],1)
        second=self.submit();self.assertFalse(second['newly_checked']);self.assertEqual(second['total_days'],1);self.assertEqual(second['coin_awarded'],0)
        self.assertTrue(self.client.get(self.path).json()['checked_today']);self.assertEqual(self.client.get('/api/wallet').json(),wallet)
        dashboard=self.client.get('/api/dashboard').json();self.assertEqual(dashboard['weekly_streak']['current'],0);self.assertFalse(any(day['qualified'] for day in dashboard['timeline']))
        self.assertEqual(self.provider.calls,0)
    def test_server_midnight_streak_gap_and_timezone_change_do_not_rewrite_attendance(self):
        self.submit();self.clock+=timedelta(minutes=2);self.assertFalse(self.client.get(self.path).json()['checked_today'])
        nextday=self.submit();self.assertEqual(nextday['today'],'2026-10-19');self.assertEqual(nextday['current_streak'],2)
        self.client.put('/api/activity/profile',json={'timezone':'America/Los_Angeles'}).raise_for_status()
        self.assertFalse(self.submit()['newly_checked']);self.clock+=timedelta(days=2);self.assertEqual(self.client.get(self.path).json()['current_streak'],0)
        later=self.submit();self.assertEqual(later['current_streak'],1);self.assertEqual(later['total_days'],3)
    def test_replay_concurrency_and_other_owner_do_not_double_count_or_leak(self):
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(lambda _:self.submit(),range(8)))
        self.assertEqual(sum(item['newly_checked'] for item in results),1)
        with TestClient(self.app,base_url='http://127.0.0.1') as other:
            other.post('/api/session').raise_for_status();self.assertFalse(other.get(self.path).json()['checked_today']);self.assertTrue(other.post(self.path,json={}).json()['newly_checked'])
        self.assertEqual(self.client.get(self.path).json()['total_days'],1)
    def test_client_cannot_spoof_date_timezone_owner_or_get_reward_by_opening(self):
        for body in [{'date':'2030-01-01'},{'timezone':'Pacific/Auckland'},{'owner_id':'other'},{'coin_awarded':99}]:
            self.assertEqual(self.client.post(self.path,json=body).status_code,422)
        for _ in range(3):self.assertFalse(self.client.get(self.path).json()['checked_today'])
        with self.app.state.database.connection() as db:self.assertEqual(db.execute("select count(*) from activity_events where kind='daily_check_in'").fetchone()[0],0)
