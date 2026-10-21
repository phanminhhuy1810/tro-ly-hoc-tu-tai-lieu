"""Audit the saved one-shot vision output and exercise QA-only manual review.

No inference is performed. The nine reference rows were compared with the
rendered original PDF page by Codex, not an independent human reviewer.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import httpx

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
output = HERE / 'results/page24-review-audit.json'
if output.exists():
    raise SystemExit('Audit exists; inspect its saved IDs instead of applying again.')
trial = json.loads((HERE / 'results/page24-vision.json').read_text())
assert trial['status'] == 'succeeded' and trial['applied'] is False
proposal = trial['proposal']; raw = proposal['text']
expected = [('0' * 8, 0)] + [('1' * n + '0' * (8 - n), 256 - 2 ** (8 - n)) for n in range(1, 9)]
rows = []
for line in raw.splitlines():
    cells = [c.strip() for c in line.strip().strip('|').split('|')]
    if len(cells) == 10 and all(c in {'0', '1'} for c in cells[:8]) and cells[8] == '=':
        rows.append((''.join(cells[:8]), int(cells[9])))
assert rows == expected, rows
assert all(int(bits, 2) == decimal for bits, decimal in rows)
header = '| 128 | 64 | 32 | 16 | 8 | 4 | 2 | 1 |'
separator = '| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |'
assert header in raw and separator in raw
# Only repair the Markdown column count; no generated bit or answer changes.
edited = raw.replace(header, header + ' = | Giá trị |', 1).replace(separator, separator + ' :--- | :--- |', 1)
report = {
    'purpose': 'Agent-assisted image/table audit and manual extraction preview/apply on a separate QA image source.',
    'at': datetime.now(timezone.utc).isoformat(), 'qa_source_id': proposal['source_id'],
    'model': trial['model'], 'inference_calls_during_audit': 0, 'external_inference': 0,
    'independent_human_reviewed': False, 'reviewer': 'Codex visual inspection plus program arithmetic',
    'rows_observed_in_image': expected, 'ai_rows': rows, 'matching_numeric_rows': len(rows),
    'numeric_rows_total': 9, 'raw_markdown_header_columns': 8, 'raw_markdown_body_columns': 10,
    'raw_output_perfect': False, 'manual_changes': ['Add two missing Markdown header/separator cells; preserve all generated table values.'],
    'native_ocr_dropped_zero_cells': True, 'native_ocr_is_not_complete_table': True,
    'uncertain_spans_empty_is_not_proof_of_correct_layout': not proposal['uncertain_spans'],
    'raw_ai_text_sha256': hashlib.sha256(raw.encode()).hexdigest(), 'checks': {},
}
image = ROOT / 'backend/runtime/chapter-visual-audit/page-24.png'
private = ROOT / 'backend/runtime/chapter-visual-audit/qa-session.json'
with httpx.Client(base_url='http://127.0.0.1:8770', cookies=json.loads(private.read_text()), timeout=30, trust_env=False) as client:
    def call(method, path, body=None):
        response = client.request(method, '/api' + path, json=body)
        response.raise_for_status(); return response.json()
    source_path = '/sources/' + proposal['source_id']
    before = call('GET', source_path)
    assert before['revision'] == 1 and not before['reviewed']
    wallet = call('GET', '/wallet')
    child = call('POST', '/source-proposals/' + proposal['id'] + '/edit-preview', {'expected_revision': 1, 'text': edited})
    report['manual_proposal_id'] = child['id']
    report['checks']['preview_does_not_change_source'] = call('GET', source_path) == before
    applied = call('POST', '/source-proposals/' + child['id'] + '/apply', {'expected_revision': 1, 'page': 1})
    assert applied['revision'] == 2 and not applied['reviewed']
    report['checks']['apply_still_requires_confirmation'] = True
    reviewed = call('POST', source_path + '/review', {'expected_revision': 2, 'texts': [f['text'] for f in applied['fragments']]})
    report['checks']['qa_revision3_reviewed'] = reviewed['revision'] == 3 and reviewed['reviewed']
    report['checks']['ai_parent_text_unchanged'] = call('GET', '/source-proposals/' + proposal['id'])['text'] == raw
    original = client.get('/api' + source_path + '/original'); original.raise_for_status()
    report['checks']['original_raster_unchanged'] = hashlib.sha256(original.content).hexdigest() == trial['raster_sha256'] == hashlib.sha256(image.read_bytes()).hexdigest()
    report['checks']['native_revision_preserved'] = call('GET', source_path + '?revision=1')['fragments'] == before['fragments']
    report['checks']['no_coin_change_for_manual_review'] = call('GET', '/wallet') == wallet
    report['checks']['manual_provenance_keeps_ai_parent'] = all(
        f.get('provenance', {}).get('parent_proposal_id') == proposal['id'] for f in reviewed['fragments'])
    report['reviewed_source'] = reviewed
assert all(report['checks'].values()), report['checks']
output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'checks': len(report['checks']), 'numeric_rows': len(rows), 'layout_manual_fix': True, 'qa_revision': 3}))
