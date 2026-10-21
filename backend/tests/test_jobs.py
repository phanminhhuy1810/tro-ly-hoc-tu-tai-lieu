import asyncio
import httpx

from test_slice import SliceFixture
from study_backend.models import Outline


class JobTests(SliceFixture):
    def test_duplicate_request_keeps_one_plan_and_one_provider_call(self):
        source = self.source()
        source = self.client.post(f"/api/sources/{source['id']}/review", json={"expected_revision": 1, "texts": [f["text"] for f in source["fragments"]]}).json()
        body = self.preferences(source)

        async def scenario():
            started, release = asyncio.Event(), asyncio.Event()
            previous_generate = self.provider.generate

            async def blocked(schema, instruction, fragments):
                started.set(); await release.wait()
                return await previous_generate(schema, instruction, fragments)

            self.provider.generate = blocked
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://127.0.0.1", cookies=self.client.cookies) as client:
                first_task = asyncio.create_task(client.post('/api/plans', json=body, headers={"Idempotency-Key": "same-intent"}))
                await asyncio.wait_for(started.wait(), 2)
                second = await client.post('/api/plans', json=body, headers={"Idempotency-Key": "same-intent"})
                # Another tab without a key still reuses the active job.
                third = await client.post('/api/plans', json=body)
                self.assertEqual(second.json(), third.json())
                with self.app.state.database.connection() as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM plans').fetchone()[0], 1)
                    self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0], 1)
                release.set(); first = await first_task
                self.assertEqual(first.json(), second.json())
                replay = await client.post('/api/plans', json=body, headers={"Idempotency-Key": "same-intent"})
                self.assertEqual(replay.json(), first.json())
                mismatch = await client.post('/api/plans', json={**body, "goal": "Another goal"}, headers={"Idempotency-Key": "same-intent"})
                self.assertEqual(mismatch.status_code, 409)
                self.assertEqual(self.provider.calls, 1)
        asyncio.run(scenario())

    def test_cancel_has_no_late_commit_and_does_not_touch_another_user(self):
        source = self.source()
        source = self.client.post(f"/api/sources/{source['id']}/review", json={"expected_revision": 1, "texts": [f["text"] for f in source["fragments"]]}).json()

        async def scenario():
            started = asyncio.Event(); previous = self.provider.generate

            async def blocked(schema, instruction, fragments):
                started.set(); await asyncio.Event().wait()
                return await previous(schema, instruction, fragments)

            self.provider.generate = blocked
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://127.0.0.1", cookies=self.client.cookies) as client:
                pending = asyncio.create_task(client.post('/api/plans', json=self.preferences(source)))
                await asyncio.wait_for(started.wait(), 2)
                with self.app.state.database.connection() as db:
                    job_id = db.execute('SELECT id FROM jobs').fetchone()[0]
                    plan_id = db.execute('SELECT id FROM plans').fetchone()[0]
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://127.0.0.1") as outsider:
                    await outsider.post('/api/session')
                    self.assertEqual((await outsider.post(f'/api/jobs/{job_id}/cancel')).status_code, 404)
                cancelled = await client.post(f'/api/jobs/{job_id}/cancel')
                self.assertEqual(cancelled.json()['status'], 'cancelled')
                await asyncio.wait_for(pending, 2)
                self.assertEqual((await client.get(f'/api/jobs/{job_id}')).json()['status'], 'cancelled')
                self.assertEqual((await client.get(f'/api/plans/{plan_id}')).json()['status'], 'failed')
                self.assertEqual((await client.get(f'/api/sources/{source["id"]}')).json()['reviewed'], True)
        asyncio.run(scenario())

    def test_finished_job_replay_does_not_generate_again_or_allow_cancel(self):
        course = self.course()
        body = {"unit_id": "unit-1", "message": "Hint"}
        path = f"/api/courses/{course['id']}/chat"
        response = self.client.post(path, json=body, headers={"Idempotency-Key": "chat-once"})
        self.job(response)
        calls = self.provider.calls
        replay = self.client.post(path, json=body, headers={"Idempotency-Key": "chat-once"})
        self.assertEqual(replay.json(), response.json())
        self.assertEqual(self.provider.calls, calls)
        self.assertEqual(len(self.client.get(path).json()), 2)
        self.assertEqual(self.client.post('/api/jobs/' + response.json()['job_id'] + '/cancel').status_code, 409)

    def test_local_capacity_rejects_new_intent_before_prepare_and_allows_explicit_retry(self):
        source = self.source()
        source = self.client.post('/api/sources/' + source['id'] + '/review', json={'expected_revision': 1, 'texts': [f['text'] for f in source['fragments']]}).json()
        first_body = self.preferences(source);second_body = {**first_body, 'goal': 'Another scope'}
        async def scenario():
            started, release = asyncio.Event(), asyncio.Event()
            generate = self.provider.generate
            async def blocked(*args):
                started.set();await release.wait();return await generate(*args)
            self.provider.generate = blocked
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://127.0.0.1', cookies=self.client.cookies) as client:
                pending = asyncio.create_task(client.post('/api/plans', json=first_body))
                await asyncio.wait_for(started.wait(), 2)
                refused = await client.post('/api/plans', json=second_body)
                self.assertEqual(refused.status_code, 429)
                self.assertEqual(refused.json()['detail']['code'], 'AI_BUSY')
                with self.app.state.database.connection() as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM plans').fetchone()[0], 1)
                release.set();await pending
                retry = await client.post('/api/plans', json=second_body)
                self.assertEqual(retry.status_code, 200)
        asyncio.run(scenario())

