"""One explicit QA completion after an incompatible v1 focus caused a decline.

No regeneration of the reading or previous questions, and no change to the
measured dev-v5 report. The new ordering is checked against original steps.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[2]; HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'backend'))
from study_backend.ordering import verify_ordering

out = HERE / 'results/ftc-ordering-recovery.json'
assert not out.exists(), 'Inspect saved IDs instead of repeating generation'
raw_path = ROOT / 'experiments/08-quality-evaluation/results/dev-v5-chapter-focus.json'
raw = raw_path.read_bytes(); run = json.loads(raw)
case = next(c for c in run['runs'] if c['case_id'] == 'calc-dev-ftc')
cid, uid = case['course_id'], case['unit_id']; old = case['course_snapshot']['content']['units'][0]
assert len(old['data']['questions']) == 6 and any(x['stage'] == 'ordering' and x['origin'] == 'model_declined' for x in old['generation']['question_coverage']['uncreated'])
with sqlite3.connect('file:' + str(ROOT / 'backend/runtime/study.sqlite3') + '?mode=ro', uri=True) as db:
    assert not db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running')").fetchone()
report = {'purpose': 'Separate post-fix completion, not a replacement for the dev-v5 measurement or a new quality score.',
          'at': datetime.now(timezone.utc).isoformat(), 'case_id': case['case_id'], 'course_id': cid, 'unit_id': uid,
          'dev_raw_sha256': hashlib.sha256(raw).hexdigest(), 'limits': {'completion_jobs': 1, 'seconds': 210},
          'external_inference': 0, 'automatic_semantic_retries': 0, 'independent_human_reviews': 0, 'checks': {}}
def save(): out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
cookie = ROOT / 'backend/runtime/quality-evaluation/dev-v5-chapter-focus/calc-dev-ftc.json'
with httpx.Client(base_url='http://127.0.0.1:8770/api', trust_env=False, timeout=20, cookies=json.loads(cookie.read_text())) as client:
    def call(method, path, body=None, headers=None):
        r = client.request(method, path, json=body, headers=headers); r.raise_for_status(); return r.json()
    before = call('GET', '/courses/' + cid + '/editor'); assert before['revision'] == 2
    assert before['content']['units'][0]['data'] == old['data']
    public = call('GET', '/courses/' + cid)['content']['units'][0]['generation']
    report['checks']['private_plan_not_in_read_view'] = 'question_focus_plan' not in public and 'stage_focus' not in public
    chapter = call('GET', '/courses/' + cid + '/chapter-context?unit_id=' + uid); assert chapter['complete']
    with sqlite3.connect('file:' + str(ROOT / 'backend/runtime/study.sqlite3') + '?mode=ro', uri=True) as db:
        nodes = db.execute('SELECT nodes_json FROM chapter_contexts WHERE id=?', (chapter['context_id'],)).fetchone()[0]
    session = call('GET', '/sessions/' + case['session_id']); report['wallet_before'] = call('GET', '/wallet'); save()
    body = {'expected_revision': 2, 'unit_id': uid, 'stages': ['ordering']}
    headers = {'Idempotency-Key': 'v26-ftc-kind-compatible-ordering'}
    response = client.post('/courses/' + cid + '/question-completion', json=body, headers=headers)
    if response.status_code == 402:
        quote = response.json()['detail']; assert quote['amount'] <= 4 and quote['model'] == 'gemma4:12b-mlx'
        report['quote_amount'] = quote['amount']; headers['Coin-Quote-Id'] = quote['quote_id']
        response = client.post('/courses/' + cid + '/question-completion', json=body, headers=headers)
    response.raise_for_status(); jid = response.json()['job_id']; report['job_id'] = jid; save()
    print(json.dumps({'job_id': jid, 'status': 'started'}), flush=True); started = time.monotonic()
    while True:
        job = call('GET', '/jobs/' + jid)
        if job['status'] in {'succeeded', 'failed', 'cancelled'}: break
        if time.monotonic() - started > 205:
            call('POST', '/jobs/' + jid + '/cancel'); job = call('GET', '/jobs/' + jid); break
        time.sleep(.5)
    report.update(job=job, status=job['status'], elapsed_seconds=round(time.monotonic() - started, 3)); save()
    report['checks']['old_course_unchanged_before_apply'] = call('GET', '/courses/' + cid + '/editor') == before
    if job['status'] == 'succeeded' and (job.get('result') or {}).get('proposal_id'):
        pid = job['result']['proposal_id']; preview = call('GET', '/proposals/' + pid); report['preview'] = preview
        questions = preview['after']['questions']; assert len(questions) == 7 and questions[:-1] == old['data']['questions']
        q = questions[-1]; assert q['kind'] == 'ordering'; verify_ordering(q, case['source_snapshot']['fragments'])
        report['checks']['new_order_proved_from_original_steps'] = True
        call('POST', '/proposals/' + pid + '/apply', {'expected_revision': 2})
        after = call('GET', '/courses/' + cid + '/editor'); new = after['content']['units'][0]
        history = new['generation']['question_completion_history'][-1]
        report['applied_revision'] = after['revision']; report['new_question'] = q
        report['checks']['old_questions_and_reading_unchanged'] = new['data']['questions'][:-1] == old['data']['questions'] and all(new['data'][k] == old['data'][k] for k in ('title','sections','cards','mindmap'))
        report['checks']['kind_compatible_focus_recorded'] = history['question_focus_plan']['assignments']['ordering']['basis'] == 'explicit_source_sequence'
        report['checks']['old_focus_provenance_unchanged'] = new['generation']['question_focus_plan'] == old['generation']['question_focus_plan']
        report['checks']['old_session_unchanged'] = call('GET', '/sessions/' + case['session_id']) == session
    with sqlite3.connect('file:' + str(ROOT / 'backend/runtime/study.sqlite3') + '?mode=ro', uri=True) as db:
        report['checks']['chapter_not_read_again'] = nodes == db.execute('SELECT nodes_json FROM chapter_contexts WHERE id=?', (chapter['context_id'],)).fetchone()[0]
    report['checks']['one_ordering_request'] = [r['schema'] for r in job['progress']['requests']] == ['OrderingDraft']
    report['checks']['source_unchanged'] = call('GET', '/sources/' + case['source_id']) == case['source_snapshot']
    report['checks']['original_measurement_retained'] = raw_path.read_bytes() == raw
    report['wallet_after'] = call('GET', '/wallet'); save()
assert report.get('applied_revision') == 3 and all(report['checks'].values()), 'Retain failed/partial diagnostic; no automatic retry'
print(json.dumps({'status': report['status'], 'seconds': report['elapsed_seconds'], 'checks': report['checks']}), flush=True)
