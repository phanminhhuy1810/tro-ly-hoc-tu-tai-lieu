"""One bounded local correction preview for an already flagged development item.

Never overwrite the original measurement, automatically retry a semantic failure,
apply a preview, change model selection, or read/release held-out final outputs.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import time

import httpx

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / 'results/operant-correction-preview.json'
assert not OUT.exists(), 'Observe saved job ID; do not repeat a model request.'
OUT.parent.mkdir(exist_ok=True)
raw_path = ROOT / 'experiments/08-quality-evaluation/results/dev-v5-chapter-focus.json'
raw = raw_path.read_bytes()
case = next(c for c in json.loads(raw)['runs'] if c['case_id'] == 'psy-dev-operant')
cid, uid, index = case['course_id'], case['unit_id'], 4
database = ROOT / 'backend/runtime/study.sqlite3'
with sqlite3.connect('file:' + str(database) + '?mode=ro', uri=True) as db:
    assert not db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running')").fetchone()
    assert db.execute('SELECT model_id FROM ai_preferences WHERE owner_id=?', (case['qa_owner_id'],)).fetchone()[0] == 'local:gemma4:12b-mlx'

report = {'purpose': 'One source-crosschecked correction preview, separate from original development measurements and independent human evaluation.',
          'at': datetime.now(timezone.utc).isoformat(), 'case_id': case['case_id'], 'course_id': cid,
          'question_index': index, 'dev_raw_sha256': hashlib.sha256(raw).hexdigest(),
          'limits': {'correction_jobs': 1, 'seconds': 210}, 'external_inference': 0,
          'automatic_semantic_retries': 0, 'independent_human_reviews': 0, 'model_quality_pass': None, 'checks': {}}
def save(): OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')

cookie = ROOT / 'backend/runtime/quality-evaluation/dev-v5-chapter-focus/psy-dev-operant.json'
with httpx.Client(base_url='http://127.0.0.1:8770/api', trust_env=False, timeout=20, cookies=json.loads(cookie.read_text())) as client:
    def call(method, path, body=None, headers=None):
        r = client.request(method, path, json=body, headers=headers); r.raise_for_status(); return r.json()
    before = call('GET', '/courses/' + cid + '/editor')
    assert before['revision'] == 2 and before['content']['units'][0]['data'] == case['course_snapshot']['content']['units'][0]['data']
    question = before['content']['units'][0]['data']['questions'][index]
    assert question['kind'] == 'short_answer' and 'giữ lại quyền' in question['prompt']
    chapter = call('GET', '/courses/' + cid + '/chapter-context?unit_id=' + uid); assert chapter['complete']
    with sqlite3.connect('file:' + str(database) + '?mode=ro', uri=True) as db:
        nodes = db.execute('SELECT nodes_json FROM chapter_contexts WHERE id=?', (chapter['context_id'],)).fetchone()[0]
    old_session = call('GET', '/sessions/' + case['session_id'])
    old_job = call('GET', '/jobs/' + case['job_id'])
    report.update(before_question=question, chapter_before=chapter, wallet_before=call('GET', '/wallet'))
    body = {'expected_revision': before['revision'], 'unit_id': uid, 'target': 'question', 'index': index,
            'request': "Giữ nguyên đề bài và tình huống học sinh được giữ lại quyền dùng máy tính; chỉ sửa đáp án tham khảo, lời giải và rubric. Không biến 'được giữ quyền' thành 'bị thu hồi'. Phân tích hành vi mục tiêu và thêm/loại bỏ kích thích theo chương. Nếu thiếu dữ kiện để kết luận duy nhất thì nói rõ chưa đủ, không cố bảo vệ nhãn negative punishment. Giữ dạng short_answer."}
    report['request'] = body; save()
    headers = {'Idempotency-Key': 'whole-chapter-operant-correction-once-v3'}
    response = client.post('/courses/' + cid + '/proposals', json=body, headers=headers)
    if response.status_code == 402:
        quote = response.json()['detail']; assert quote['amount'] <= 2 and quote['model'] == 'gemma4:12b-mlx'
        report['quote_amount'] = quote['amount']; headers['Coin-Quote-Id'] = quote['quote_id']
        response = client.post('/courses/' + cid + '/proposals', json=body, headers=headers)
    response.raise_for_status(); jid = response.json()['job_id']; report['job_id'] = jid; save()
    print(json.dumps({'job_id': jid, 'status': 'started'}), flush=True); start = time.monotonic()
    while True:
        job = call('GET', '/jobs/' + jid)
        if job['status'] in {'succeeded', 'failed', 'cancelled'}: break
        if time.monotonic() - start > 205:
            call('POST', '/jobs/' + jid + '/cancel'); job = call('GET', '/jobs/' + jid); break
        time.sleep(.5)
    report.update(job=job, status=job['status'], elapsed_seconds=round(time.monotonic() - start, 3))
    report['checks']['course_unchanged_before_apply'] = call('GET', '/courses/' + cid + '/editor') == before
    if job['status'] == 'succeeded' and (job.get('result') or {}).get('proposal_id'):
        report['preview'] = call('GET', '/proposals/' + job['result']['proposal_id'])
        report['checks']['only_selected_question_preview'] = report['preview']['scope'] == {'unit_id': uid, 'target': 'question', 'index': index}
        report['checks']['stem_kept_exactly'] = report['preview']['after']['prompt'] == question['prompt']
        report['checks']['kind_kept'] = report['preview']['after']['kind'] == question['kind']
    report['checks']['old_attempt_unchanged'] = call('GET', '/sessions/' + case['session_id']) == old_session
    report['checks']['original_job_unchanged'] = call('GET', '/jobs/' + case['job_id']) == old_job
    report['checks']['source_unchanged'] = call('GET', '/sources/' + case['source_id']) == case['source_snapshot']
    report['checks']['original_measurement_retained'] = raw_path.read_bytes() == raw
    report['checks']['no_chapter_reading_request'] = all(r['schema'] != 'ChapterBrief' for r in job['progress']['requests'])
    report['checks']['one_short_answer_request'] = [r['schema'] for r in job['progress']['requests']] == ['ShortAnswerDraft']
    with sqlite3.connect('file:' + str(database) + '?mode=ro', uri=True) as db:
        report['checks']['chapter_cache_unchanged'] = nodes == db.execute('SELECT nodes_json FROM chapter_contexts WHERE id=?', (chapter['context_id'],)).fetchone()[0]
    report['wallet_after'] = call('GET', '/wallet')
    report['checks']['no_coin_held'] = report['wallet_after']['held'] == 0
    save()
print(json.dumps({'status': report['status'], 'seconds': report['elapsed_seconds'], 'checks': report['checks']}), flush=True)
