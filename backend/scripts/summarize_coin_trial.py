"""Export the single observed browser Coin trial, restricted to our dev source."""
import hashlib
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
JOB = 'ceeae2a1e92e4a43ae851565eb7f306b'
SOURCE = 'c44feeece5c441089388b6ef88cd4b1d'
original = (ROOT / 'backend/runtime/sources' / SOURCE).read_bytes()
assert original == (ROOT / 'experiments/02-local-ai/fixtures/subnet-dev.txt').read_bytes()
with sqlite3.connect((ROOT / 'backend/runtime/study.sqlite3').as_uri() + '?mode=ro', uri=True) as db:
    db.row_factory = sqlite3.Row
    job = db.execute('SELECT * FROM jobs WHERE id=?', (JOB,)).fetchone()
    owner = db.execute('SELECT owner_id FROM sources WHERE id=?', (SOURCE,)).fetchone()[0]
    assert job['owner_id'] == owner and job['task'] == 'chat' and job['status'] == 'succeeded'
    usage = db.execute('SELECT * FROM ai_usage WHERE job_id=?', (JOB,)).fetchone()
    quote = db.execute('SELECT * FROM coin_quotes WHERE id=?', (usage['quote_id'],)).fetchone()
    reservation = db.execute('SELECT amount,status FROM coin_reservations WHERE job_id=?', (JOB,)).fetchone()
    spend = db.execute('SELECT amount,created_at FROM coin_ledger WHERE owner_id=? AND event_key=?', (owner, 'ai-spend:' + JOB)).fetchall()
    assert len(spend) == 1 and spend[0]['amount'] == -1 and reservation['status'] == usage['status'] == 'committed'
    assert quote['created_at'] < job['created_at']
    messages = [dict(r) for r in db.execute('SELECT role,content,refs_json,revision,created_at FROM chat_messages WHERE owner_id=? AND course_id=? AND created_at>=? AND created_at<=? ORDER BY created_at', (owner, json.loads(job['payload_json'])['course_id'], job['created_at'], job['updated_at']))]
    report = {'verified_at': datetime.now(timezone.utc).isoformat(),
              'scope': 'Real browser/local Qwen 9B on exact self-authored subnet fixture; UI and read-only DB observations; not independent human/quality evaluation',
              'job_id': JOB, 'status': job['status'], 'provider': json.loads(job['payload_json'])['_provider'],
              'source_sha256': hashlib.sha256(original).hexdigest(),
              'browser_observations': {'before_confirm_ai_usage_count': 0, 'cancel_kept_draft': True, 'compact_to_full_kept_draft': True,
                                       'wallet_before': 20, 'wallet_after_ai_saved': 19, 'confirmation_required': True},
              'quote': {'created_at': quote['created_at'], 'amount': quote['amount'], 'status': quote['status'], 'policy': json.loads(quote['policy_json'])},
              'reservation': dict(reservation), 'debit_rows_for_job': [dict(r) for r in spend], 'chat_saved_in_job_window': messages,
              'seconds': round((datetime.fromisoformat(job['updated_at']) - datetime.fromisoformat(job['created_at'])).total_seconds(), 3),
              'screenshots': ['frontend/screenshots/local-coin-confirmation.png', 'frontend/screenshots/local-coin-ledger.png'],
              'cash_payment': False, 'passed': True}
    balance = db.execute('SELECT balance FROM wallets WHERE owner_id=?', (owner,)).fetchone()[0]
    ledger_sum = db.execute('SELECT sum(amount) FROM coin_ledger WHERE owner_id=?', (owner,)).fetchone()[0]
    assert balance == ledger_sum
    report['wallet_now_including_later_activity'] = balance
target = ROOT / 'backend/evidence/coin-browser-trial.json'
target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'report': str(target), 'passed': True, 'debit_rows': len(spend), 'amount': spend[0]['amount'], 'current_balance': balance}))
