"""One explicit post-fix resume of the failed QA lesson, preserving old evidence."""
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
from study_backend.models import Question
from study_backend.question_quality import verify_mcq_options
from study_backend.polynomial_questions import CompositionError

out = HERE / 'results/chain-resume-v26.json'; assert not out.exists(), 'Observe saved job ID, never repeat this resume'
raw_path = ROOT / 'experiments/08-quality-evaluation/results/dev-v5-chapter-focus.json'
raw = raw_path.read_bytes(); run = json.loads(raw)
case = next(c for c in run['runs'] if c['case_id'] == 'calc-dev-chain')
assert case['job']['status'] == 'failed' and case['published_question_count'] == 0
cid, uid = case['course_id'], case['unit_id']; partial = case['job']['partial']
old_questions = {k: v['question'] for k, v in partial['questions'].items() if v.get('question')}
valid, rejected = {}, {}
for key, q in old_questions.items():
    try: verify_mcq_options(q)
    except CompositionError as exc: rejected[key] = exc.code
    else: valid[key] = Question.model_validate(q).model_dump()
assert rejected == {'mcq': 'MCQ_COMPOSITION_NOT_UNIQUE'} and len(valid) == 3
with sqlite3.connect('file:' + str(ROOT / 'backend/runtime/study.sqlite3') + '?mode=ro', uri=True) as db:
    assert not db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running')").fetchone()
    assert db.execute('SELECT model_id FROM ai_preferences WHERE owner_id=?', (case['qa_owner_id'],)).fetchone()[0] == 'local:gemma4:12b-mlx'
    context_id = partial['chapter_context']['context_id']
    nodes = db.execute('SELECT nodes_json FROM chapter_contexts WHERE id=?', (context_id,)).fetchone()[0]
report = {'purpose': 'Separate explicit QA recovery after new validator/prompt; never relabel the old failed development measurement.',
          'at': datetime.now(timezone.utc).isoformat(), 'case_id': case['case_id'], 'course_id': cid,
          'old_job_id': case['job_id'], 'dev_raw_sha256': hashlib.sha256(raw).hexdigest(),
          'old_rejected_candidates': rejected, 'valid_saved_question_stages': list(valid),
          'limits': {'resume_jobs': 1, 'seconds': 210}, 'external_inference': 0, 'automatic_semantic_retries': 0,
          'independent_human_reviews': 0, 'model_quality_pass': None, 'checks': {}}
def save(): out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
cookie = ROOT / 'backend/runtime/quality-evaluation/dev-v5-chapter-focus/calc-dev-chain.json'
with httpx.Client(base_url='http://127.0.0.1:8770/api', trust_env=False, timeout=20, cookies=json.loads(cookie.read_text())) as client:
    def call(method, path, body=None, headers=None):
        r = client.request(method, path, json=body, headers=headers); r.raise_for_status(); return r.json()
    before = call('GET', '/courses/' + cid + '/editor'); assert before['revision'] == 1 and before['content']['units'][0]['data'] is None
    old_job = call('GET', '/jobs/' + case['job_id']); assert old_job == case['job']
    report['wallet_before'] = call('GET', '/wallet'); save()
    body = {'expected_revision': 1, 'unit_id': uid, 'resume_job_id': case['job_id']}
    headers = {'Idempotency-Key': 'v26-chain-reviewed-explicit-resume'}
    response = client.post('/courses/' + cid + '/generate', json=body, headers=headers)
    if response.status_code == 402:
        quote = response.json()['detail']; assert quote['amount'] <= 10 and quote['model'] == 'gemma4:12b-mlx'
        headers['Coin-Quote-Id'] = quote['quote_id']; report['quote_amount'] = quote['amount']
        response = client.post('/courses/' + cid + '/generate', json=body, headers=headers)
    response.raise_for_status(); jid = response.json()['job_id']; report['job_id'] = jid; save()
    print(json.dumps({'job_id': jid, 'status': 'started'}), flush=True); started = time.monotonic()
    while True:
        job = call('GET', '/jobs/' + jid)
        if job['status'] in {'succeeded', 'failed', 'cancelled'}: break
        if time.monotonic() - started > 205:
            call('POST', '/jobs/' + jid + '/cancel'); job = call('GET', '/jobs/' + jid); break
        time.sleep(.5)
    report.update(job=job, status=job['status'], elapsed_seconds=round(time.monotonic() - started, 3))
    after = call('GET', '/courses/' + cid + '/editor'); report['course_snapshot'] = after
    report['checks']['old_job_retained'] = call('GET', '/jobs/' + case['job_id']) == old_job
    report['checks']['original_measurement_retained'] = raw_path.read_bytes() == raw
    report['checks']['source_unchanged'] = call('GET', '/sources/' + case['source_id']) == case['source_snapshot']
    requests = job['progress']['requests']
    report['checks']['no_reading_or_chapter_regeneration'] = all(r['schema'] not in {'ChapterBrief', 'LessonReading'} for r in requests)
    with sqlite3.connect('file:' + str(ROOT / 'backend/runtime/study.sqlite3') + '?mode=ro', uri=True) as db:
        report['checks']['chapter_cache_unchanged'] = nodes == db.execute('SELECT nodes_json FROM chapter_contexts WHERE id=?', (context_id,)).fetchone()[0]
    if job['status'] == 'succeeded':
        unit = after['content']['units'][0]; data = unit['data']; report['question_count'] = len(data['questions'])
        report['checks']['reading_cards_mindmap_unchanged'] = all(data[k] == partial['reading'][k] for k in ('title','sections','cards','mindmap'))
        report['checks']['valid_saved_questions_preserved'] = all(q in data['questions'] for q in valid.values())
        old_bad = Question.model_construct(**old_questions['mcq']).model_dump()
        report['checks']['ambiguous_old_candidate_not_published'] = old_bad not in data['questions']
        report['checks']['old_focus_plan_stays_v1'] = unit['generation']['question_focus_plan'] == partial['question_focus_plan']
        report['checks']['old_valid_stage_providers_preserved'] = all(unit['generation']['stage_providers'][k] == partial['stage_providers'][k] for k in valid)
    report['wallet_after'] = call('GET', '/wallet'); report['checks']['no_coin_held'] = report['wallet_after']['held'] == 0; save()
print(json.dumps({'status': report['status'], 'seconds': report['elapsed_seconds'], 'questions': report.get('question_count'), 'checks': report['checks']}), flush=True)
assert report['status'] == 'succeeded' and all(report['checks'].values()), 'Keep the failed/partial recovery; no automatic retry'
