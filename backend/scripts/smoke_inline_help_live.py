"""Real local Qwen help, pinned to a question and its unsubmitted selection.

Uses only the earlier self-authored OCR fixture and its script-owned profile.
No browser credentials, external service, fake clock or mocked model.
"""
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
              'scope': 'Real local HTTP and Qwen; script-controlled development profile, not a quality benchmark or independent human trial',
              'source_id': previous['source_id'], 'original_sha256': hashlib.sha256(original).hexdigest(), 'checks': {}}
    target = ROOT / 'backend/evidence/inline-help-live-trial.json'
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8770', trust_env=False, timeout=20) as client:
        client.cookies.update(json.loads((ROOT / 'backend/runtime/smoke-learning-session.json').read_text()))

        async def api(method, path, body=None, headers=None):
            response = await client.request(method, '/api' + path, json=body, headers=headers)
            response.raise_for_status()
            return response.json()

        base = '/courses/' + previous['course_id']
        course = await api('GET', base + '/editor')
        assert course['access_role'] == 'creator'
        unit = course['content']['units'][0]
        chat_before = await api('GET', base + '/chat')
        session = await api('POST', base + '/sessions', {'expected_revision': course['revision'], 'unit_id': unit['id'], 'question_types': ['mcq', 'cloze'], 'question_count': 2}, {'Idempotency-Key': 'inline-gizmo-dev-session-v1'})
        report.update(course_id=course['id'], revision=course['revision'], session_id=session['id'])
        q, other_q = session['questions'][:2]
        fixed = next(x for x in unit['data']['questions'] if x['prompt'] == q['prompt'])
        wrong = next(i for i, option in enumerate(q['options']) if option != fixed['answer'])
        thread = (await api('POST', f"/sessions/{session['id']}/items/{q['id']}/help"))['thread_id']
        other = (await api('POST', f"/sessions/{session['id']}/items/{other_q['id']}/help"))['thread_id']
        path = '/help/threads/' + thread
        current = await api('GET', '/sessions/' + session['id'])
        await api('PUT', '/sessions/' + session['id'] + '/draft', {'item_id': q['id'], 'answer': 'option-' + str(wrong), 'expected_version': current['drafts'].get(q['id'], {}).get('version', 0)})
        before = await api('GET', '/wallet')
        explanation = await api('POST', path + '/actions', {'action': 'explain'})
        assert explanation['ai_called'] is False
        assert (await api('POST', path + '/actions', {'action': 'explain'}))['cached']
        assert await api('GET', '/wallet') == before
        assert not (await api('GET', '/sessions/' + session['id']))['answers']
        report['checks']['saved_explanation_before_answer_free_and_no_fake_submission'] = True
        snapshot = await api('GET', path)
        message = 'Giải thích vì sao lựa chọn mình đang chọn khác đáp án tham khảo của câu này. Dựa vào nguồn và nói ngắn gọn.'
        await api('PUT', path + '/draft', {'text': message, 'expected_version': snapshot['draft']['version']})
        body = {'action': 'ask', 'message': message}
        headers = {'Idempotency-Key': 'inline-gizmo-dev-question-v1'}
        response = await client.post('/api' + path + '/actions', json=body, headers=headers)
        if response.status_code == 402:
            quote = response.json()['detail']
            assert quote['code'] == 'COIN_CONFIRMATION_REQUIRED'
            assert (await api('GET', path))['draft']['text'] == message
            assert (await api('GET', path))['messages'] == snapshot['messages']
            report['quote'] = {k: quote[k] for k in ['amount', 'model']}
            report['checks']['quote_before_new_message_or_ai_job'] = True
            headers['Coin-Quote-Id'] = quote['quote_id']
            response = await client.post('/api' + path + '/actions', json=body, headers=headers)
        response.raise_for_status()
        job_id = response.json()['job_id'];report['job_id'] = job_id
        print(json.dumps({'job_id': job_id, 'question': q['prompt'], 'selected_option': q['options'][wrong]}, ensure_ascii=False), flush=True)
        # Move to another question while the original request is still running.
        other_path = '/help/threads/' + other
        other_before = await api('GET', other_path)
        await api('PUT', other_path + '/draft', {'text': 'Bản nháp riêng của câu kế tiếp', 'expected_version': other_before['draft']['version']})
        for _ in range(105):
            job = await api('GET', '/jobs/' + job_id)
            if job['status'] in {'failed', 'cancelled', 'succeeded'}:
                break
            await asyncio.sleep(2)
        report['job'] = job
        report['wallet_before'] = before
        report['wallet_after'] = await api('GET', '/wallet')
        after = await api('GET', path);other_after = await api('GET', other_path)
        report['question_context'] = after['context'];report['student'] = after['student']
        report['messages'] = after['messages'];report['source_excerpts'] = after['source_excerpts']
        report['checks']['next_question_draft_and_messages_stay_separate'] = other_after['messages'] == [] and other_after['draft']['text'] == 'Bản nháp riêng của câu kế tiếp'
        report['checks']['global_chat_unchanged'] = await api('GET', base + '/chat') == chat_before
        report['checks']['unsubmitted_selection_kept'] = not after['student']['submitted'] and after['student']['draft'] == 'option-' + str(wrong)
        report['checks']['job_replay_no_second_charge'] = (await api('POST', path + '/actions', body, headers))['job_id'] == job_id and (await api('GET', '/wallet')) == report['wallet_after']
        report['checks']['reply_saved_to_original_question'] = job['status'] == 'succeeded' and job['result']['thread_id'] == thread and after['messages'][-1]['role'] == 'assistant'
        report['checks']['successful_draft_cleared'] = job['status'] == 'succeeded' and after['draft']['text'] == ''
        report['passed'] = all(report['checks'].values()) and job['status'] == 'succeeded'
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'report': str(target), 'passed': report['passed'], 'status': job['status'], 'checks': report['checks'], 'reply': job.get('result')}, ensure_ascii=False))
        assert report['passed'], 'Inspect the saved trial; do not automatically call the model again'


if __name__ == '__main__':
    asyncio.run(main())
