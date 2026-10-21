"""Bounded Gemini/HTTP development trial; no browser cookie or key extraction.

Creates its own anonymous QA profile and two self-authored text documents.
--confirm-coin explicitly allows at most 5 proposed app Coin in this QA run.
It does not buy credits, enable billing, retry generation, or change defaults.
"""
import argparse
import asyncio
import copy
import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
report = {'purpose': 'Per-unit source/extraction binding over real HTTP and Gemini; self-authored development documents, not a quality benchmark or human trial',
          'started_at': datetime.now(timezone.utc).isoformat(), 'checks': {}, 'jobs': [], 'coin_confirmed': 0}


async def main(confirm_coin):
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8770', timeout=25, trust_env=False) as client:
        async def api(method, path, body=None):
            response = await client.request(method, '/api' + path, json=body)
            response.raise_for_status()
            return response.json()

        async def job(path, body):
            headers = {'Idempotency-Key': uuid.uuid4().hex}
            response = await client.post('/api' + path, json=body, headers=headers)
            if response.status_code == 402:
                quote = response.json()['detail']
                report.setdefault('quotes', []).append({k: quote.get(k) for k in ('code', 'amount', 'model', 'provider')})
                if not confirm_coin or report['coin_confirmed'] + quote['amount'] > 5:
                    raise RuntimeError('Coin confirmation required or QA Coin limit reached; no generation retry sent.')
                headers['Coin-Quote-Id'] = quote['quote_id']
                response = await client.post('/api' + path, json=body, headers=headers)
                if response.is_success:
                    report['coin_confirmed'] += quote['amount']
            response.raise_for_status()
            identity = response.json()['job_id']
            started = time.monotonic()
            while time.monotonic() - started < 220:
                value = await api('GET', '/jobs/' + identity)
                if value['status'] in {'succeeded', 'failed', 'cancelled'}:
                    report['jobs'].append({'id': identity, 'status': value['status'], 'provider': value['provider'],
                                           'error': value.get('error'), 'elapsed_seconds': round(time.monotonic() - started, 3),
                                           'partial': value.get('partial') if value['status'] != 'succeeded' else None})
                    if value['status'] != 'succeeded':
                        raise RuntimeError('AI job ended ' + value['status'] + '; saved stage/error retained, no automatic retry.')
                    return value['result']
                await asyncio.sleep(0.5)
            report['still_observing_job_id'] = identity
            raise RuntimeError('Observation timed out; job state must be checked before any restart or retry.')

        async def source(name, text):
            value = await api('POST', '/sources/text', {'name': name, 'text': text})
            return await api('POST', '/sources/' + value['id'] + '/review',
                             {'expected_revision': value['revision'], 'texts': [f['text'] for f in value['fragments']]})

        async def publish(course):
            preview = await api('POST', '/courses/' + course['id'] + '/publication-preview',
                                {'expected_revision': course['revision'], 'visibility': 'shared', 'share_original': True})
            return await api('POST', '/publications/' + preview['publication_id'] + '/apply', {'expected_revision': course['revision']})

        await api('POST', '/session')
        private = ROOT / 'backend/runtime/source-binding-qa-session.json'
        private.write_text(json.dumps(dict(client.cookies)))
        private.chmod(0o600)
        models = await api('GET', '/ai/models')
        selected = next(m for m in models['models'] if m['id'] == 'gemini:gemini-2.5-flash')
        if not selected['ready']:
            raise RuntimeError('Configured Gemini is unavailable; no provider fallback.')
        await api('PUT', '/ai/selection', {'model_id': selected['id'], 'expected_revision': models['selection_revision'], 'allow_external': True})
        text_a = 'IPv4 dùng địa chỉ dài 32 bit.\nMột địa chỉ IPv4 có bốn octet, mỗi octet dài 8 bit.\nVí dụ dạng thập phân có dấu chấm: 192.168.1.70.'
        text_b = 'IPv6 dùng địa chỉ dài 128 bit.\nDạng đầy đủ của IPv6 có tám nhóm số hexa, ngăn bằng dấu hai chấm.\nVí dụ dạng đầy đủ: 2001:0db8:0000:0000:0000:0000:0000:0001.'
        first = await source('QA-source-A-IPv4.txt', text_a)
        second = await source('QA-source-B-IPv6.txt', text_b)
        refs_a = [f['id'] for f in first['fragments']]
        prefs = {'source_id': first['id'], 'expected_extraction_revision': first['revision'], 'fragment_ids': refs_a,
                 'subject': 'Mạng máy tính', 'goal': 'Học cách biểu diễn địa chỉ IP, mỗi bài dùng đúng nguồn đã duyệt.',
                 'language': 'vi', 'unlock_policy': 'open', 'question_types': ['mcq'], 'question_count': 1, 'card_count': 1}
        plan_id = (await job('/plans', prefs))['plan_id']
        plan = await api('GET', '/plans/' + plan_id)
        outline = {'title': 'QA — hai nguồn IP độc lập', 'units': [
            {'title': 'Địa chỉ IPv4', 'objective': 'Nhận biết IPv4 dài 32 bit, bốn octet và cách biểu diễn.', 'source_refs': refs_a},
            {'title': 'Phần tiếp chưa tạo', 'objective': 'Chờ chọn nguồn trước khi tạo nội dung phần tiếp.', 'source_refs': refs_a}]}
        plan = await api('PUT', '/plans/' + plan_id, {'expected_version': plan['outline']['version'], 'outline': outline})
        course_id = (await api('POST', '/plans/' + plan_id + '/approve', {'expected_revision': plan['outline']['version']}))['course_id']
        report['course_id'] = course_id
        path = '/courses/' + course_id
        await job(path + '/generate', {'expected_revision': 1, 'unit_id': 'unit-1'})
        course = await api('GET', path + '/editor')
        learned = copy.deepcopy(course['content']['units'][0])
        report['first_question'] = learned['data']['questions'][0]
        assert set(report['first_question']['source_refs']) <= set(refs_a)
        attempt = await api('POST', path + '/sessions', {'expected_revision': course['revision'], 'unit_id': 'unit-1'})
        q = learned['data']['questions'][0]
        result = await api('POST', '/sessions/' + attempt['id'] + '/answers',
                           {'item_id': attempt['questions'][0]['id'], 'answer': 'option-' + str(q['options'].index(q['answer']))})
        assert result['correct'] is True
        old_result = await api('POST', '/sessions/' + attempt['id'] + '/complete')
        report['session_id'] = attempt['id']
        await publish(course)
        invite = await api('POST', path + '/invite')

        async def preview(source):
            return await api('POST', path + '/future-plan-preview', {'expected_revision': course['revision'],
                'units': [{'unit_id': 'unit-2', 'title': 'Địa chỉ IPv6', 'objective': 'Nhận biết IPv6 dài 128 bit và cách biểu diễn tám nhóm hexa.',
                           'source_id': source['id'], 'expected_extraction_revision': source['revision'], 'source_refs': [f['id'] for f in source['fragments']]}],
                'request': 'QA chỉ đổi nguồn bài 2; bài 1 và lịch sử giữ nguyên.'})

        stale = await preview(second)
        second = await api('POST', '/sources/' + second['id'] + '/review',
                           {'expected_revision': second['revision'], 'texts': [f['text'] for f in second['fragments']]})
        response = await client.post('/api/proposals/' + stale['proposal_id'] + '/apply', json={'expected_revision': course['revision']})
        assert response.status_code == 409
        report['checks']['source_edited_after_preview_blocks_stale_apply'] = True
        await api('POST', '/proposals/' + stale['proposal_id'] + '/discard')
        proposed = await preview(second)
        viewed = await api('GET', '/proposals/' + proposed['proposal_id'])
        report['source_bindings_preview'] = viewed['source_bindings']
        assert (await api('GET', path))['revision'] == course['revision']
        assert viewed['after']['units'][0]['data'] == learned['data']
        report['checks']['preview_keeps_live_course_and_learned_data'] = True
        applied = await api('POST', '/proposals/' + proposed['proposal_id'] + '/apply', {'expected_revision': course['revision']})
        await job(path + '/generate', {'expected_revision': applied['revision'], 'unit_id': 'unit-2'})
        course = await api('GET', path + '/editor')
        report['final_revision'] = course['revision']
        report['bindings'] = (await api('GET', path + '/source-bindings'))['units']
        report['second_question'] = course['content']['units'][1]['data']['questions'][0]
        report['checks']['second_question_only_new_source_refs'] = set(report['second_question']['source_refs']) <= {f['id'] for f in second['fragments']}
        assert report['checks']['second_question_only_new_source_refs']
        assert course['content']['units'][0]['data'] == learned['data']
        assert (await api('GET', '/sessions/' + attempt['id']))['result'] == old_result
        report['checks']['learned_data_and_result_unchanged'] = True
        original = await client.get('/api/sources/' + first['id'] + '/original')
        assert original.content == text_a.encode()
        report['original_a_sha256'] = hashlib.sha256(original.content).hexdigest()
        await job(path + '/chat', {'unit_id': 'unit-1', 'session_id': attempt['id'], 'item_id': attempt['questions'][0]['id'],
                                  'message': 'Giải thích lại câu IPv4 này theo nguồn của lượt cũ, dù bài tiếp đã chuyển sang IPv6.'})
        chat = (await api('GET', path + '/chat'))[-1]
        assert set(chat['source_refs']) <= set(refs_a) and chat['revision'] == attempt['revision']
        report['old_attempt_chat'] = chat
        report['checks']['old_attempt_chat_uses_original_refs_and_revision'] = True
        async with httpx.AsyncClient(base_url=str(client.base_url), timeout=25, trust_env=False) as peer:
            (await peer.post('/api/session')).raise_for_status()
            (await peer.post('/api/community/join', json={'code': invite['code']})).raise_for_status()
            response = await peer.get('/api/sources/' + second['id'] + '/original')
            assert response.status_code == 404
            report['checks']['new_original_not_auto_shared'] = True
            fragments = await peer.get('/api' + path + '/source-fragments?unit_id=unit-2')
            fragments.raise_for_status()
            assert {f['id'] for f in fragments.json()} == {f['id'] for f in second['fragments']}
            report['checks']['enrolled_peer_sees_selected_ready_excerpts'] = True
        # This is a development course; remove it from community after the trial.
        private_preview = await api('POST', path + '/publication-preview', {'expected_revision': course['revision'], 'visibility': 'private'})
        await api('POST', '/publications/' + private_preview['publication_id'] + '/apply', {'expected_revision': course['revision']})
        report['checks']['trial_course_returned_to_private'] = True
        report['passed'] = True


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--confirm-coin', action='store_true')
    args = parser.parse_args()
    try:
        asyncio.run(main(args.confirm_coin))
    except Exception as exc:
        report.update(passed=False, error_type=type(exc).__name__, error=str(exc))
    finally:
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        output = ROOT / 'backend/evidence/source-binding-live-trial.json'
        if output.exists():
            previous = json.loads(output.read_text())
            report['previous_attempts'] = previous.pop('previous_attempts', []) + [previous]
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'passed': report.get('passed'), 'checks': report['checks'],
                          'jobs': [{k: v for k, v in job.items() if k != 'partial'} for job in report['jobs']],
                          'error': report.get('error'), 'report': str(output)}, ensure_ascii=False))
