"""Read-only export of the observed inline-help trial on our exact dev source."""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = 'c44feeece5c441089388b6ef88cd4b1d'
MESSAGE = 'Vì sao địa chỉ mình chọn là broadcast chứ không phải network?'
original = (ROOT / 'backend/runtime/sources' / SOURCE).read_bytes()
assert original == (ROOT / 'experiments/02-local-ai/fixtures/subnet-dev.txt').read_bytes()
with sqlite3.connect((ROOT / 'backend/runtime/study.sqlite3').as_uri() + '?mode=ro', uri=True) as db:
    db.row_factory = sqlite3.Row
    owner = db.execute('SELECT owner_id FROM sources WHERE id=?', (SOURCE,)).fetchone()[0]
    matches = [r for r in db.execute("SELECT * FROM jobs WHERE owner_id=? AND task='inline_help' AND status='succeeded'", (owner,)) if json.loads(r['payload_json']).get('message') == MESSAGE]
    assert len(matches) == 1, 'Export only the one observed request'
    job = matches[0];payload = json.loads(job['payload_json'])
    thread = db.execute('SELECT * FROM help_threads WHERE id=? AND owner_id=?', (payload['thread_id'], owner)).fetchone()
    context = json.loads(thread['context_json'])
    assert all(f['id'].startswith(SOURCE + ':') for f in context['fragments'])
    messages = [dict(r) for r in db.execute('SELECT role,action,content_json,created_at FROM help_messages WHERE thread_id=? ORDER BY created_at', (thread['id'],))]
    for m in messages:m['content'] = json.loads(m.pop('content_json'))
    reservation = dict(db.execute('SELECT amount,status FROM coin_reservations WHERE job_id=?', (job['id'],)).fetchone())
    debit = [dict(r) for r in db.execute('SELECT amount,created_at FROM coin_ledger WHERE owner_id=? AND event_key=?', (owner, 'ai-spend:' + job['id']))]
    assert len(debit) == 1 and debit[0]['amount'] == -1 and reservation['status'] == 'committed'
    assert payload['student']['draft_display'] == '192.168.1.127' and not payload['student']['submitted']
    assert db.execute('SELECT count(*) FROM answers WHERE session_id=?', (context['session_id'],)).fetchone()[0] == 0
    assistant_id = json.loads(job['result_json'])['message_id']
    saved_note = db.execute("SELECT n.id,n.label,n.refs_json FROM notebook_origins o JOIN notebook_entries n ON n.id=o.entry_id WHERE o.owner_id=? AND o.kind='inline_help' AND o.origin_id=?", (owner, assistant_id)).fetchall()
    saved_card = db.execute('SELECT id,version FROM personal_cards WHERE owner_id=? AND origin_key=? AND deleted_at IS NULL', (owner, context['question']['question_revision_id'])).fetchall()
    assert len(saved_note) == len(saved_card) == 1 and saved_note[0]['label'] == 'ai'
    report = {'verified_at': datetime.now(timezone.utc).isoformat(),
              'scope': 'Browser and read-only DB on self-authored dev source with real local Qwen; not independent human or general quality evaluation',
              'source_sha256': hashlib.sha256(original).hexdigest(), 'job_id': job['id'], 'provider': payload['_provider'],
              'course_revision': thread['course_revision'], 'question': context['question']['prompt'],
              'student_snapshot': payload['student'], 'reply': json.loads(job['result_json']),
              'seconds': round((datetime.fromisoformat(job['updated_at']) - datetime.fromisoformat(job['created_at'])).total_seconds(), 3),
              'browser_observations': {'selected_option_survives_help_open_and_reload': True,
                                       'cached_explanation_available_before_submitting': True,
                                       'coin_cancel_keeps_draft': True, 'confirmed_new_ai_reply_shown_inline': True,
                                       'successful_help_draft_cleared': True, 'save_note_and_card_confirmed_in_ui': True},
              'saved_note': {'id': saved_note[0]['id'], 'label': saved_note[0]['label'], 'source_refs': json.loads(saved_note[0]['refs_json'])},
              'saved_card': dict(saved_card[0]),
              'question_answer_count': 0, 'reservation': reservation, 'debits': debit, 'messages': messages,
              'screenshot': 'frontend/screenshots/local-inline-help.png', 'cash_payment': False, 'passed': True}
target = ROOT / 'backend/evidence/inline-help-browser-trial.json'
target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'report': str(target), 'passed': True, 'job_id': job['id'], 'seconds': report['seconds'], 'reply': report['reply']['text']}, ensure_ascii=False))
