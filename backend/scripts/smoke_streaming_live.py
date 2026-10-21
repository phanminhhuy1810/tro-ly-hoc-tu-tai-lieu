"""Real loopback/Gemini/local-9B stream smoke test with isolated QA profiles.

Reuses a self-authored dev course; never submits keys, changes AI defaults,
starts Kaggle, or retries generation. --confirm-coin permits at most 3 proposed
app Coin including a reservation cancelled during a streamed draft.
"""
import argparse
import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / 'backend/evidence/streaming-live-trial.json'
result = {'started_at': datetime.now(timezone.utc).isoformat(), 'purpose': 'Real HTTP/native stream smoke test, self-authored IPv4 source; two script profiles, not a human trial or quality benchmark',
          'runs': [], 'confirmed_coin': 0}
QUESTION = 'Giải thích trong khoảng 150–180 từ mối liên hệ giữa 32 bit, bốn octet và cách viết địa chỉ IPv4 có dấu chấm. Dùng ví dụ đúng trong nguồn. Chia thành ba ý rõ, chỉ suy luận từ các dữ kiện được cung cấp, không thêm chủ đề ngoài nguồn.'


async def api(client, method, path, body=None):
    response = await client.request(method, '/api' + path, json=body)
    response.raise_for_status()
    return response.json()


async def start(client, path, message):
    body = {'unit_id': 'unit-1', 'message': message}
    headers = {'Idempotency-Key': uuid.uuid4().hex}
    response = await client.post('/api' + path + '/chat', json=body, headers=headers)
    if response.status_code == 402:
        quote = response.json()['detail']
        if result['confirmed_coin'] + quote['amount'] > 3:
            raise RuntimeError('QA Coin budget reached; request not confirmed.')
        headers['Coin-Quote-Id'] = quote['quote_id']
        response = await client.post('/api' + path + '/chat', json=body, headers=headers)
        if response.is_success: result['confirmed_coin'] += quote['amount']
    response.raise_for_status()
    return response.json()['job_id']


async def observe(client, job_id, run, started, cancel=False):
    terminal = None; cursor = 0; cancel_sent = False
    while time.monotonic() - started < 220:
        headers = {'Last-Event-ID': str(cursor)} if cursor else {}
        async with client.stream('GET', '/api/jobs/' + job_id + '/events', headers=headers, timeout=35) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith('data: '): continue
                value = json.loads(line[6:])
                if not value.get('status'): raise RuntimeError('Observation lost access; job handle retained: ' + job_id)
                p = value.get('progress') or {}; cursor = p.get('version', cursor)
                preview = (p.get('preview') or {}).get('text', '')
                elapsed = round(time.monotonic() - started, 3)
                run.setdefault('events', []).append({'seconds': elapsed, 'status': value['status'], 'phase': p.get('phase'),
                                                    'version': cursor, 'preview_characters': len(preview)})
                if preview and value['status'] == 'running' and run.get('first_visible_seconds') is None:
                    run['first_visible_seconds'] = elapsed
                    repeated = await client.get('/api/jobs/' + job_id + '/events?once=true', headers={'Last-Event-ID': str(cursor)})
                    repeated.raise_for_status()
                    check = json.loads(next(x[6:] for x in repeated.text.splitlines() if x.startswith('data: ')))
                    assert check['id'] == job_id
                    run['reconnect_same_job'] = True
                    if cancel:
                        cancelled = await api(client, 'POST', '/jobs/' + job_id + '/cancel')
                        assert cancelled['status'] == 'cancelled'
                        cancel_sent = True
                if value['status'] in {'succeeded', 'failed', 'cancelled'}:
                    terminal = value; break
        if terminal: break
    if terminal is None:
        result['still_observing_job_id'] = job_id
        raise RuntimeError('Observation timeout; inspect this same job before any retry/restart.')
    run.update(status=terminal['status'], completed_seconds=round(time.monotonic() - started, 3),
               provider=terminal['provider'], progress=terminal['progress'], error=terminal['error'],
               preview_before_completion=run.get('first_visible_seconds') is not None)
    if cancel:
        run['cancel_sent'] = cancel_sent
        assert cancel_sent and terminal['status'] == 'cancelled'
        assert terminal['result'] is None and terminal['progress']['preview'] is None
        await asyncio.sleep(0.5)
        assert (await api(client, 'GET', '/jobs/' + job_id))['status'] == 'cancelled'
    else:
        assert terminal['status'] == 'succeeded', terminal.get('error')
        run['reply'] = terminal['result']
    return terminal


async def main():
    previous = json.loads((ROOT / 'backend/evidence/source-binding-live-trial.json').read_text())
    course_id = previous['course_id']; path = '/courses/' + course_id
    clients = []
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8770', timeout=25, trust_env=False) as owner:
        owner.cookies.update(json.loads((ROOT / 'backend/runtime/source-binding-qa-session.json').read_text()))
        course = await api(owner, 'GET', path + '/editor')
        result['course_id'] = course_id
        source_refs = set(course['content']['units'][0]['source_refs'])
        preview = await api(owner, 'POST', path + '/publication-preview', {'expected_revision': course['revision'], 'visibility': 'shared', 'share_original': False})
        await api(owner, 'POST', '/publications/' + preview['publication_id'] + '/apply', {'expected_revision': course['revision']})
        invite = await api(owner, 'POST', path + '/invite')
        try:
            for label, model in [('gemini', 'gemini:gemini-2.5-flash'), ('local9b', 'local:qwen3.5:9b')]:
                client = httpx.AsyncClient(base_url=str(owner.base_url), timeout=25, trust_env=False); clients.append(client)
                await api(client, 'POST', '/session')
                private = ROOT / ('backend/runtime/streaming-' + label + '-qa-session.json')
                private.write_text(json.dumps(dict(client.cookies))); private.chmod(0o600)
                catalog = await api(client, 'GET', '/ai/models')
                await api(client, 'PUT', '/ai/selection', {'model_id': model, 'expected_revision': catalog['selection_revision'], 'allow_external': model.startswith('gemini:')})
                await api(client, 'POST', '/community/join', {'code': invite['code']})
                run = {'model_choice': model, 'same_source_same_prompt_empty_history': True}
                result['runs'].append(run)
                started = time.monotonic(); identity = await start(client, path, QUESTION)
                run['job_id'] = identity
                await observe(client, identity, run, started)
                assert set(run['reply']['source_refs']) <= source_refs
                history = await api(client, 'GET', path + '/chat')
                assert len(history) == 2
                run['one_saved_user_and_answer'] = True
                print(json.dumps({'model': model, 'first_visible_seconds': run.get('first_visible_seconds'), 'completed_seconds': run['completed_seconds'], 'status': run['status']}, ensure_ascii=False), flush=True)
            client = clients[-1]
            before = await api(client, 'GET', '/wallet')
            run = {'model_choice': 'local:qwen3.5:9b', 'purpose': 'Cancel after first visible draft'}; result['runs'].append(run)
            started = time.monotonic(); identity = await start(client, path, QUESTION + ' Giải thích kỹ hơn trong khoảng 350 từ.')
            run['job_id'] = identity
            await observe(client, identity, run, started, cancel=True)
            after = await api(client, 'GET', '/wallet')
            assert after['held'] == 0 and after['balance'] == before['balance']
            history = await api(client, 'GET', path + '/chat')
            assert [m['role'] for m in history] == ['user', 'assistant', 'user']
            run['wallet_unchanged_no_late_answer'] = True
            result['passed'] = True
        finally:
            for client in clients: await client.aclose()
            preview = await api(owner, 'POST', path + '/publication-preview', {'expected_revision': course['revision'], 'visibility': 'private'})
            await api(owner, 'POST', '/publications/' + preview['publication_id'] + '/apply', {'expected_revision': course['revision']})
            result['course_returned_private'] = True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--confirm-coin', action='store_true', required=True); parser.parse_args()
    try: asyncio.run(main())
    except Exception as exc: result.update(passed=False, error_type=type(exc).__name__, error=str(exc))
    finally:
        result['finished_at'] = datetime.now(timezone.utc).isoformat()
        if REPORT.exists():
            previous = json.loads(REPORT.read_text()); result['previous_attempts'] = previous.pop('previous_attempts', []) + [previous]
        REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'passed': result.get('passed'), 'error': result.get('error'), 'report': str(REPORT)}, ensure_ascii=False), flush=True)
