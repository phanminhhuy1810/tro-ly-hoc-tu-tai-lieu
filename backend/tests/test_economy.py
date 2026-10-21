import asyncio
from datetime import timedelta
import httpx
from fastapi.testclient import TestClient
from test_slice import SliceFixture


class EconomyTests(SliceFixture):
    def setUp(self):
        super().setUp()
        self.course_value=self.course()
        self.economy=self.app.state.economy
        self.economy.enabled=True
        self.owner=self.client.post('/api/session').json()['id']
        self.path=f"/api/courses/{self.course_value['id']}/chat"
        self.body={'unit_id':'unit-1','message':'A source-grounded hint'}

    def quote(self,body=None,key='paid-once'):
        response=self.client.post(self.path,json=body or self.body,headers={'Idempotency-Key':key})
        self.assertEqual(response.status_code,402,response.text)
        self.assertEqual(response.json()['detail']['code'],'COIN_CONFIRMATION_REQUIRED')
        return response.json()['detail']

    def test_quote_is_before_ai_and_confirmed_replay_spends_once(self):
        calls=self.provider.calls;quoted=self.quote()
        self.assertEqual(self.provider.calls,calls)
        self.assertEqual(self.client.get(self.path).json(),[])
        self.assertEqual(self.client.get('/api/wallet').json()['available'],20)
        self.assertEqual(self.quote()['quote_id'],quoted['quote_id'])
        headers={'Idempotency-Key':'paid-once','Coin-Quote-Id':quoted['quote_id']}
        created=self.client.post(self.path,json=self.body,headers=headers);self.job(created)
        wallet=self.client.get('/api/wallet').json()
        self.assertEqual((wallet['balance'],wallet['held'],wallet['available']),(19,0,19))
        self.assertEqual(self.client.post(self.path,json=self.body,headers=headers).json(),created.json())
        ledger=self.client.get('/api/wallet/history').json()['ledger']
        self.assertEqual(len([r for r in ledger if r['amount']<0]),1)
        self.assertEqual(self.provider.calls,calls+1)

    def test_quote_cannot_change_payload_expire_or_reuse_by_another_profile(self):
        quoted=self.quote();calls=self.provider.calls
        headers={'Idempotency-Key':'paid-once','Coin-Quote-Id':quoted['quote_id']}
        self.assertEqual(self.client.post(self.path,json={**self.body,'message':'different'},headers=headers).status_code,409)
        course_path = '/api/courses/' + self.course_value['id']
        preview = self.client.post(course_path + '/publication-preview', json={'expected_revision': 2, 'visibility': 'public'}).json()
        self.client.post('/api/publications/' + preview['publication_id'] + '/apply', json={'expected_revision': 2}).raise_for_status()
        with TestClient(self.app, base_url='http://127.0.0.1') as peer:
            peer.post('/api/session');peer.post(course_path + '/enroll')
            self.assertEqual(peer.post(self.path, json=self.body, headers=headers).status_code, 409)
            self.assertEqual(peer.get('/api/wallet').json()['balance'], 20)
        old=self.economy.clock;self.economy.clock=lambda:old()+timedelta(minutes=11)
        self.assertEqual(self.client.post(self.path,json=self.body,headers=headers).status_code,409)
        self.assertEqual(self.provider.calls,calls)
        self.assertEqual(self.client.get('/api/wallet').json()['held'],0)

    def test_invalid_output_refunds_and_no_source_reply_releases_instead_of_spend(self):
        async def fail(*args):raise ValueError('Output failed validation')
        self.provider.generate=fail
        quoted=self.quote();response=self.client.post(self.path,json=self.body,headers={'Idempotency-Key':'paid-once','Coin-Quote-Id':quoted['quote_id']})
        job=self.client.get('/api/jobs/'+response.json()['job_id']).json()
        self.assertEqual(job['status'],'failed')
        self.assertEqual(self.client.get('/api/wallet').json()['balance'],20)
        async def missing(schema,instruction,fragments):
            return {'text':'Need another source','source_refs':[],'needs_more_source':True}
        self.provider.generate=missing
        body={**self.body,'message':'Outside source'};quoted=self.quote(body,'missing-source')
        self.job(self.client.post(self.path,json=body,headers={'Idempotency-Key':'missing-source','Coin-Quote-Id':quoted['quote_id']}))
        wallet=self.client.get('/api/wallet').json();self.assertEqual((wallet['balance'],wallet['held']),(20,0))
        self.assertTrue(all(r['status']=='released' for r in self.client.get('/api/wallet/history').json()['reservations']))

    def test_concurrent_hold_prevents_overspend_cancel_releases_and_no_late_output(self):
        self.economy.policy['initial_coin']=1
        first=self.quote();secondbody={**self.body,'message':'A second hint'};second=self.quote(secondbody,'second')
        async def scenario():
            started=asyncio.Event()
            async def blocked(*args):started.set();await asyncio.Event().wait()
            self.provider.generate=blocked
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://127.0.0.1',cookies=self.client.cookies) as c:
                pending=asyncio.create_task(c.post(self.path,json=self.body,headers={'Idempotency-Key':'paid-once','Coin-Quote-Id':first['quote_id']}))
                await asyncio.wait_for(started.wait(),2)
                wallet=(await c.get('/api/wallet')).json();self.assertEqual((wallet['balance'],wallet['held'],wallet['available']),(1,1,0))
                refused=await c.post(self.path,json=secondbody,headers={'Idempotency-Key':'second','Coin-Quote-Id':second['quote_id']})
                self.assertEqual(refused.status_code,402);self.assertEqual(refused.json()['detail']['code'],'INSUFFICIENT_COIN')
                with self.app.state.database.connection() as db:job_id=db.execute("SELECT id FROM jobs WHERE status='running'").fetchone()[0]
                await c.post('/api/jobs/'+job_id+'/cancel')
                await asyncio.wait_for(pending,2)
                wallet=(await c.get('/api/wallet')).json();self.assertEqual((wallet['balance'],wallet['held'],wallet['available']),(1,0,1))
                self.assertEqual((await c.get('/api/jobs/'+job_id)).json()['status'],'cancelled')
                self.assertFalse(any(m['role']=='assistant' for m in (await c.get(self.path)).json()))
        asyncio.run(scenario())

    def test_reconcile_uses_terminal_state_and_is_repeatable(self):
        self.quote()
        # Seed persisted post-crash states, not an imagined timing condition.
        with self.app.state.database.connection(write=True) as db:
            template=dict(db.execute('SELECT * FROM jobs LIMIT 1').fetchone());columns=list(template)
            for suffix,status in [('failed','failed'),('saved','succeeded')]:
                values={**template,'id':'recovery-'+suffix,'status':status,'result_json':'{}'}
                db.execute('INSERT INTO jobs ('+','.join(columns)+') VALUES ('+','.join('?' for _ in columns)+')',[values[k] for k in columns])
                decision={'amount':1,'quota_group':None}
                self.economy.reserve(db,self.owner,values['id'],'chat',decision)
            self.economy.reconcile(db);self.economy.reconcile(db)
        wallet=self.client.get('/api/wallet').json();self.assertEqual((wallet['balance'],wallet['held']),(19,0))
        ledger=self.client.get('/api/wallet/history').json()['ledger'];self.assertEqual(sum(r['amount']<0 for r in ledger),1)

    def test_initial_outline_quota_is_once_failed_job_releases_it_and_policy_change_gets_new_quote(self):
        source = self.source()
        source = self.client.post('/api/sources/' + source['id'] + '/review', json={'expected_revision': 1, 'texts': [f['text'] for f in source['fragments']]}).json()
        body = self.preferences(source)
        generate = self.provider.generate
        async def unavailable(*args):raise RuntimeError('Local provider unavailable')
        self.provider.generate = unavailable
        failed = self.client.post('/api/plans', json=body)
        self.assertEqual(self.client.get('/api/jobs/' + failed.json()['job_id']).json()['status'], 'failed')
        self.provider.generate = generate
        self.job(self.client.post('/api/plans', json=body, headers={'Idempotency-Key': 'free-outline'}))
        self.assertEqual(self.client.get('/api/wallet').json()['balance'], 20)
        paid = self.client.post('/api/plans', json={**body, 'goal': 'Another objective'})
        self.assertEqual(paid.status_code, 402)
        self.assertEqual(paid.json()['detail']['amount'], 3)
        quoted = self.quote()
        self.economy.policy['version'] = 'changed-proposal'
        self.assertEqual(self.client.post(self.path, json=self.body, headers={'Idempotency-Key': 'paid-once', 'Coin-Quote-Id': quoted['quote_id']}).status_code, 409)
        refreshed = self.quote()
        self.assertNotEqual(refreshed['quote_id'], quoted['quote_id'])

    def test_zero_coin_blocks_only_new_ai_cached_source_answers_and_manual_edit_are_free(self):
        self.client.get('/api/wallet')
        with self.app.state.database.connection(write=True) as db:
            db.execute('UPDATE wallets SET balance=0 WHERE owner_id=?', (self.owner,))
        quote = self.quote()
        self.assertTrue(quote['insufficient_coin'])
        refused = self.client.post(self.path, json=self.body, headers={'Idempotency-Key': 'paid-once', 'Coin-Quote-Id': quote['quote_id']})
        self.assertEqual(refused.json()['detail']['code'], 'INSUFFICIENT_COIN')
        calls = self.provider.calls
        self.assertEqual(self.client.get('/api/courses/' + self.course_value['id']).status_code, 200)
        self.assertEqual(self.client.get('/api/cards?course_id=' + self.course_value['id']).status_code, 200)
        source = self.client.get('/api/plans/' + self.course_value['plan_id']).json()['source_id']
        self.assertEqual(self.client.get('/api/sources/' + source + '/original').status_code, 200)
        replacement = self.course_value['content']['units'][0]['data']['cards'][0].copy()
        replacement['back'] = 'Manually corrected'
        proposal = self.client.post('/api/courses/' + self.course_value['id'] + '/proposals', json={'expected_revision': 2, 'unit_id': 'unit-1', 'target': 'card', 'index': 0, 'request': 'manual', 'replacement': replacement})
        proposal.raise_for_status()
        self.assertIn('proposal_id', proposal.json())
        self.assertEqual(self.provider.calls, calls)
        self.assertEqual(self.client.get('/api/wallet').json()['balance'], 0)

    def test_rewards_are_unique_capped_and_cannot_be_farmed_by_replay(self):
        with self.app.state.database.connection(write=True) as db:
            first=self.economy.award(db,self.owner,2,'peer:one','community')
            self.assertEqual(first['amount'],2)
            self.assertTrue(self.economy.award(db,self.owner,2,'peer:one','community')['replayed'])
            self.economy.award(db,self.owner,2,'peer:two','community')
            self.assertEqual(self.economy.award(db,self.owner,2,'peer:three','community')['amount'],0)
            self.economy.award(db,self.owner,10,'milestone:one','achievement')
            self.assertEqual(self.economy.award(db,self.owner,2,'mission:one','mission')['amount'],0)
            self.assertEqual(self.economy.wallet(db,self.owner)['balance'],32)
        old=self.economy.clock;self.economy.clock=lambda:old()+timedelta(days=1)
        with self.app.state.database.connection(write=True) as db:
            self.assertTrue(self.economy.award(db,self.owner,2,'peer:three','community')['replayed'])
            self.assertEqual(self.economy.wallet(db,self.owner)['balance'],32)
