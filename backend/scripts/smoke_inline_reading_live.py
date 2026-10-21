"""One real local reading-help request on the script-owned OCR dev course."""
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]


async def main():
    previous = json.loads((ROOT / 'backend/evidence/learning-live-trial.json').read_text())
    original = (ROOT / 'backend/runtime/sources' / previous['source_id']).read_bytes()
    assert original == (ROOT / 'experiments/03-ocr-inputs/fixtures/networking.png').read_bytes()
    report = {'verified_at': datetime.now(timezone.utc).isoformat(),
              'scope': 'Real HTTP and local Qwen, script-owned self-authored dev source; not a broad quality or human trial',
              'source_sha256': hashlib.sha256(original).hexdigest(), 'checks': {}}
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8770', trust_env=False, timeout=20) as client:
        client.cookies.update(json.loads((ROOT / 'backend/runtime/smoke-learning-session.json').read_text()))
        async def api(method, path, body=None, headers=None):
            r = await client.request(method, '/api' + path, json=body, headers=headers)
            r.raise_for_status();return r.json()
        base = '/courses/' + previous['course_id']
        course = await api('GET', base)
        unit = course['content']['units'][0]
        section = unit['data']['sections'][0]
        thread = (await api('POST', base + f"/units/{unit['id']}/sections/0/help", {'expected_revision': course['revision']}))['thread_id']
        path = '/help/threads/' + thread
        snapshot = await api('GET', path)
        assert snapshot['context']['section'] == section
        assert 'question' not in snapshot['context']
        before = await api('GET', '/wallet')
        body = {'action': 'explain'};headers = {'Idempotency-Key': 'inline-reading-explain-v1'}
        r = await client.post('/api' + path + '/actions', json=body, headers=headers)
        if r.status_code == 402:
            quote = r.json()['detail'];assert quote['code'] == 'COIN_CONFIRMATION_REQUIRED'
            headers['Coin-Quote-Id'] = quote['quote_id']
            report['quote_amount'] = quote['amount']
            r = await client.post('/api' + path + '/actions', json=body, headers=headers)
        r.raise_for_status();value = r.json()
        if 'job_id' in value:
            report['job_id'] = value['job_id']
            print(json.dumps({'job_id': value['job_id'], 'section': section['title']}, ensure_ascii=False), flush=True)
            for _ in range(105):
                job = await api('GET', '/jobs/' + value['job_id'])
                if job['status'] in {'failed', 'cancelled', 'succeeded'}:break
                await asyncio.sleep(2)
            report['job'] = job
            assert job['status'] == 'succeeded', job
        after = await api('GET', path)
        wallet = await api('GET', '/wallet')
        cached = await api('POST', path + '/actions', body)
        report['checks']['explanation_cached_without_second_charge'] = cached.get('cached') is True and await api('GET', '/wallet') == wallet
        assistant = next(m for m in reversed(after['messages']) if m['role'] == 'assistant')
        note = await api('POST', path + '/notebook', {'message_id': assistant['id']})
        report['checks']['saved_note_has_server_text_sources_and_ai_label'] = assistant['content']['text'] in note['body'] and note['source_refs'] == assistant['content']['source_refs'] and note['label'] == 'ai'
        report['checks']['save_note_idempotent'] = (await api('POST', path + '/notebook', {'message_id': assistant['id']}))['id'] == note['id']
        report.update(course_id=course['id'], revision=course['revision'], thread_id=thread, context=after['context'],
                      source_excerpts=after['source_excerpts'], messages=after['messages'], note=note,
                      wallet_before=before, wallet_after=wallet)
        report['checks']['only_section_sources_in_reply'] = set(assistant['content']['source_refs']).issubset(set(section['source_refs']))
        report['passed'] = all(report['checks'].values())
        target = ROOT / 'backend/evidence/inline-reading-live-trial.json'
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'report': str(target), 'passed': report['passed'], 'checks': report['checks'], 'reply': assistant['content']['text']}, ensure_ascii=False))
        assert report['passed']


if __name__ == '__main__':asyncio.run(main())
