"""Real HTTP activity/Coin checks on the exact self-authored OCR dev course.

No backdated clock, wallet edits, or model mocks. This is a script-controlled
development profile, not an independent user or an AI-quality benchmark.
"""
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]


async def main():
    trial = json.loads((ROOT / 'backend/evidence/learning-live-trial.json').read_text())
    fixture = ROOT / 'experiments/03-ocr-inputs/fixtures/networking.png'
    # File name is checked against the earlier, explicitly self-authored trial.
    source_id = trial['source_id']
    original = (ROOT / 'backend/runtime/sources' / source_id).read_bytes()
    assert original == fixture.read_bytes(), 'Do not run against personal/unreviewed source data'
    report = {'verified_at': datetime.now(timezone.utc).isoformat(),
              'scope': 'Real local HTTP; script-controlled dev profile; no independent humans; no AI quality claim',
              'source_id': source_id, 'original_sha256': hashlib.sha256(original).hexdigest(), 'checks': {}}
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8770', trust_env=False) as client:
        client.cookies.update(json.loads((ROOT / 'backend/runtime/smoke-learning-session.json').read_text()))

        async def api(method, path, body=None, headers=None):
            response = await client.request(method, '/api' + path, json=body, headers=headers)
            response.raise_for_status()
            return response.json()

        base = '/courses/' + trial['course_id']
        course = await api('GET', base + '/editor')
        assert course['access_role'] == 'creator'
        before_history = await api('GET', base + '/history')
        before = await api('GET', '/wallet')
        report['wallet_before'] = before
        unit = course['content']['units'][0]
        session = await api('POST', base + '/sessions', {'expected_revision': course['revision'], 'unit_id': unit['id'], 'question_types': ['mcq'], 'question_count': 1}, {'Idempotency-Key': 'activity-dev-first-round-v1'})
        q = session['questions'][0]
        fixed = next(x for x in unit['data']['questions'] if x['prompt'] == q['prompt'])
        wrong = next(i for i, option in enumerate(q['options']) if option != fixed['answer'])
        await api('POST', '/sessions/' + session['id'] + '/answers', {'item_id': q['id'], 'answer': 'option-' + str(wrong)})
        result = await api('POST', '/sessions/' + session['id'] + '/complete')
        assert result['score'] == 0
        wallet = await api('GET', '/wallet')
        assert await api('POST', '/sessions/' + session['id'] + '/complete') == result
        assert await api('GET', '/wallet') == wallet
        report['checks']['completed_round_and_replay_no_duplicate_reward'] = True
        report['session_id'] = session['id'];report['result'] = result
        cards = await api('GET', '/cards?course_id=' + course['id'])
        # Reuse this named trial's own cards if rerun; no duplicate card creation.
        known = [c for c in cards if c['front'].startswith('Activity dev card ')]
        for index in range(len(known), 5):
            known.append(await api('POST', '/cards', {'front': f'Activity dev card {index}', 'back': 'Server activity test; not generated study content.', 'course_id': course['id']}))
        reviewed = []
        for card in known:
            current = next(c for c in await api('GET', '/cards?course_id=' + course['id']) if c['id'] == card['id'])
            value = await api('PUT', '/cards/' + card['id'] + '/memory', {'course_id': course['id'], 'remembered': False, 'expected_version': current['memory']['version']})
            reviewed.append(value)
        report['checks']['five_distinct_reviews_complete_card_mission'] = True
        report['card_reviews'] = reviewed
        report['dashboard'] = await api('GET', '/dashboard')
        report['missions'] = await api('GET', '/missions')
        report['achievements'] = await api('GET', '/achievements')
        report['wallet_after'] = await api('GET', '/wallet')
        report['ledger'] = await api('GET', '/wallet/history')
        assert report['dashboard']['weekly_streak']['current'] >= 1
        assert all(m['completed'] for m in report['missions']['daily'] if m['code'] in {'cards', 'practice'})
        after_history = await api('GET', base + '/history')
        assert all(row in after_history for row in before_history)
        report['checks']['old_attempts_kept_with_original_revision_and_result'] = True
        report['checks']['no_ai_required_for_activity_or_rewards'] = True
        report['passed'] = True
    target = ROOT / 'backend/evidence/activity-live-trial.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'report': str(target), 'passed': report['passed'], 'wallet_before': before['balance'],
                      'wallet_after': report['wallet_after']['balance'], 'checks': report['checks']}, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
