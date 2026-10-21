"""QA-only flags from the retained per-question Codex review. No key edits."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]
out = HERE / 'results/dev-v5-review-flags.json'
assert not out.exists(), 'Do not repeat an applied flag run'
raw_path = ROOT / 'experiments/08-quality-evaluation/results/dev-v5-chapter-focus.json'
raw = raw_path.read_bytes(); run = json.loads(raw)
summary = json.loads((HERE / 'results/dev-v5-summary.json').read_text())
assert run['all_cases_observed'] and summary['all_cases_reviewed']
report = {'purpose': 'QA-only Codex-assisted review flags, not independent human judgments or proof all keys are wrong.',
          'at': datetime.now(timezone.utc).isoformat(), 'raw_run_sha256': hashlib.sha256(raw).hexdigest(),
          'inference_calls': 0, 'independent_human_reviews': 0, 'flags': [], 'checks': {}}
with os.fdopen(os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644), 'w') as f: json.dump(report, f)
def save(): out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
for case in run['runs']:
    if not case['published_question_count']: continue
    review = json.loads((HERE / 'results/cases' / (case['case_id'] + '.json')).read_text())
    needing = [q for q in review['questions'] if q['status'] == 'needs_review']
    if not needing: continue
    cid, uid = case['course_id'], case['unit_id']
    cookie = ROOT / 'backend/runtime/quality-evaluation/dev-v5-chapter-focus' / (case['case_id'] + '.json')
    with httpx.Client(base_url='http://127.0.0.1:8770/api', trust_env=False, timeout=15, cookies=json.loads(cookie.read_text())) as client:
        def call(method, path, body=None):
            r = client.request(method, path, json=body); r.raise_for_status(); return r.json()
        before = call('GET', '/courses/' + cid + '/editor')
        unit = next(u for u in before['content']['units'] if u['id'] == uid)
        assert unit['data'] == case['course_snapshot']['content']['units'][0]['data']
        session = call('GET', '/sessions/' + case['session_id']); wallet = call('GET', '/wallet')
        for item in needing:
            q = unit['data']['questions'][item['question_index']]
            assert item['question_sha256'] == hashlib.sha256(json.dumps(q, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            flag = call('POST', '/courses/' + cid + '/question-reports', {'expected_revision': before['revision'], 'unit_id': uid,
                'item_id': uid + ':q' + str(item['question_index']), 'reason': 'QA do Codex đối chiếu; cần xem lại, chưa phải phán quyết người độc lập: ' + item['note']})
            report['flags'].append({'case_id': case['case_id'], 'question_index': item['question_index'], 'reason': item['note'], 'flag': flag}); save()
        after = call('GET', '/courses/' + cid + '/editor'); after_session = call('GET', '/sessions/' + case['session_id'])
        report['checks'][case['case_id']] = {'course_content_unchanged': before == after,
            'old_session_snapshot_unchanged': all(session[k] == after_session[k] for k in ('revision', 'questions', 'result')),
            'coin_unchanged': call('GET', '/wallet') == wallet}
        assert all(report['checks'][case['case_id']].values())
report['original_measurement_unchanged'] = raw_path.read_bytes() == raw
report['flag_count'] = len(report['flags'])
assert report['flag_count'] == summary['published_review']['needs_review'] == 10
assert report['original_measurement_unchanged']; save()
print(json.dumps({'qa_review_flags': len(report['flags']), 'courses': len(report['checks']), 'raw_history_coin_unchanged': True, 'inference_calls': 0}))
