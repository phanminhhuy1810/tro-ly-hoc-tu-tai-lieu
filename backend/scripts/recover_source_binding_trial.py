"""Explicit one-time recovery of the saved failed source-binding QA job.

Keeps the failed run in evidence and reuses its reading; never rebuilds a course.
Requires --confirm-coin for a maximum of 2 proposed app Coin (no money/billing).
"""
import argparse
import asyncio
import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'backend/evidence/source-binding-live-trial.json'


async def recover(report):
    recovery = {'started_at': datetime.now(timezone.utc).isoformat(), 'jobs': [], 'checks': {}, 'confirmed_coin': 0}
    report.setdefault('recoveries', []).append(recovery)
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8770', timeout=25, trust_env=False) as client:
        client.cookies.update(json.loads((ROOT / 'backend/runtime/source-binding-qa-session.json').read_text()))
        async def api(method, path, body=None):
            response = await client.request(method, '/api' + path, json=body)
            response.raise_for_status()
            return response.json()
        async def job(path, body):
            headers = {'Idempotency-Key': uuid.uuid4().hex}
            response = await client.post('/api' + path, json=body, headers=headers)
            if response.status_code == 402:
                quote = response.json()['detail']
                if recovery['confirmed_coin'] + quote['amount'] > 2:
                    raise RuntimeError('Explicit recovery Coin budget exceeded; no request confirmed.')
                headers['Coin-Quote-Id'] = quote['quote_id']
                response = await client.post('/api' + path, json=body, headers=headers)
                if response.is_success:
                    recovery['confirmed_coin'] += quote['amount']
            response.raise_for_status()
            identity = response.json()['job_id']; started = time.monotonic()
            while time.monotonic() - started < 220:
                value = await api('GET', '/jobs/' + identity)
                if value['status'] in {'succeeded', 'failed', 'cancelled'}:
                    recovery['jobs'].append({'id': identity, 'status': value['status'], 'provider': value['provider'],
                                             'error': value.get('error'), 'elapsed_seconds': round(time.monotonic() - started, 3)})
                    if value['status'] != 'succeeded':
                        raise RuntimeError('Recovery job failed; no additional retry.')
                    return value
                await asyncio.sleep(0.5)
            recovery['still_observing_job_id'] = identity
            raise RuntimeError('Observation timeout; check same job before any restart/retry.')
        course_id = report['course_id']; path = '/courses/' + course_id
        course = await api('GET', path + '/editor')
        failed = next(j for j in reversed(report['jobs']) if j['status'] == 'failed')
        old_job = await api('GET', '/jobs/' + failed['id'])
        assert old_job['status'] == 'failed' and old_job['partial']['reading']
        assert not course['content']['units'][1].get('data')
        original_reading = old_job['partial']['reading']
        original_lesson = course['content']['units'][0]['data']
        attempt = await api('GET', '/sessions/' + report['session_id'])
        old_result = attempt['result']
        before = await api('GET', '/wallet')
        assert before['held'] == 0
        recovery['checks']['failed_job_has_no_outstanding_coin_hold'] = True
        generated = await job(path + '/generate', {'expected_revision': course['revision'], 'unit_id': 'unit-2', 'resume_job_id': failed['id']})
        course = await api('GET', path + '/editor')
        second = course['content']['units'][1]
        assert {k: second['data'][k] for k in original_reading} == original_reading
        recovery['checks']['reading_reused_exactly'] = True
        assert second['generation']['resumed_from_job_id'] == failed['id']
        assert second['generation']['stage_providers']['reading']['schema_version'] == 12
        recovery['stage_providers'] = second['generation']['stage_providers']
        bindings = (await api('GET', path + '/source-bindings'))['units']
        refs_a, refs_b = set(bindings[0]['source_refs']), set(bindings[1]['source_refs'])
        assert refs_a.isdisjoint(refs_b)
        assert set(second['data']['questions'][0]['source_refs']) <= refs_b
        assert course['content']['units'][0]['data'] == original_lesson
        assert (await api('GET', '/sessions/' + report['session_id']))['result'] == old_result
        recovery['checks']['new_question_refs_old_lesson_and_result_preserved'] = True
        report['bindings'] = bindings
        report['second_question'] = second['data']['questions'][0]
        report['final_revision'] = course['revision']
        original = await client.get('/api/sources/' + bindings[0]['source_id'] + '/original')
        original.raise_for_status()
        report['original_a_sha256'] = hashlib.sha256(original.content).hexdigest()
        await job(path + '/chat', {'unit_id': 'unit-1', 'session_id': report['session_id'], 'item_id': attempt['questions'][0]['id'],
                                  'message': 'Giải thích lại câu IPv4 theo nguồn của lượt cũ, dù bài tiếp đã chuyển sang IPv6.'})
        chat = (await api('GET', path + '/chat'))[-1]
        assert set(chat['source_refs']) <= refs_a and chat['revision'] == attempt['revision']
        report['old_attempt_chat'] = chat
        recovery['checks']['old_attempt_chat_keeps_original_refs_and_revision'] = True
        invite = await api('POST', path + '/invite')
        async with httpx.AsyncClient(base_url=str(client.base_url), timeout=25, trust_env=False) as peer:
            (await peer.post('/api/session')).raise_for_status()
            (await peer.post('/api/community/join', json={'code': invite['code']})).raise_for_status()
            response = await peer.get('/api/sources/' + bindings[1]['source_id'] + '/original')
            assert response.status_code == 404
            fragments = await peer.get('/api' + path + '/source-fragments?unit_id=unit-2')
            fragments.raise_for_status()
            assert {f['id'] for f in fragments.json()} == refs_b
            recovery['checks']['peer_reads_ready_excerpts_but_new_original_not_auto_shared'] = True
        private = await api('POST', path + '/publication-preview', {'expected_revision': course['revision'], 'visibility': 'private'})
        await api('POST', '/publications/' + private['publication_id'] + '/apply', {'expected_revision': course['revision']})
        recovery['checks']['trial_course_returned_to_private'] = True
        recovery.update(passed=True, finished_at=datetime.now(timezone.utc).isoformat(), wallet_after=await api('GET', '/wallet'))
        report['passed_after_explicit_recovery'] = True


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--confirm-coin', action='store_true', required=True)
    parser.parse_args()
    report = json.loads(OUTPUT.read_text())
    try:
        asyncio.run(recover(report))
    except Exception as exc:
        report['recoveries'][-1].update(passed=False, error_type=type(exc).__name__, error=str(exc))
    finally:
        OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(report['recoveries'][-1], ensure_ascii=False))
