"""Offline aggregate, retaining failed cases and distinguishing unpublished work."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
raw_path = ROOT / 'experiments/08-quality-evaluation/results/dev-v5-chapter-focus.json'
raw = raw_path.read_bytes(); trial = json.loads(raw)
assert trial['all_cases_observed'] and len(trial['runs']) == 6
report = {'purpose': 'Development workflow/quality review, not an independent factual accuracy score or release.',
          'at': datetime.now(timezone.utc).isoformat(), 'raw_run_sha256': hashlib.sha256(raw).hexdigest(),
          'run_id': trial['run_id'], 'production_sha256': trial['production_sha256'],
          'protocol_sha256': trial['protocol_sha256'], 'cases': [], 'target_questions': 48,
          'semantic_retries': trial['semantic_retries'], 'external_inference': trial['external_inference'],
          'independent_human_reviews': 0, 'factual_accuracy_score': None, 'release_ready': False}
published_status, partial_status, uncreated, kinds = Counter(), Counter(), Counter(), Counter()
for case in trial['runs']:
    review_path = HERE / 'results/cases' / (case['case_id'] + '.json')
    review = json.loads(review_path.read_text())
    assert review['source_sha256'] == case['source_sha256']
    assert review['production_sha256'] == trial['production_sha256']
    unit = case['course_snapshot']['content']['units'][0]
    questions = (unit['data'] or {}).get('questions', [])
    published = bool(unit['data'])
    if not published:
        questions = [v['question'] for v in case['job']['partial'].get('questions', {}).values() if v.get('question')]
    assert len(questions) == len(review['questions'])
    for q, checked in zip(questions, review['questions']):
        assert checked['question_sha256'] == hashlib.sha256(json.dumps(q, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        (published_status if published else partial_status)[checked['status']] += 1
        if published: kinds[q['kind']] += 1
    if published:
        for missing in unit['generation']['question_coverage']['uncreated']: uncreated[missing['origin']] += 1
    else: uncreated['failed_case_unpublished_targets'] += 8
    report['cases'].append({'case_id': case['case_id'], 'job_status': case['job']['status'],
        'published_questions': case['published_question_count'], 'saved_partial_questions': 0 if published else len(questions),
        'chapter_complete': case['chapter_context']['complete'], 'elapsed_ms': case['job']['progress'].get('elapsed_ms'),
        'review_path': str(review_path.relative_to(ROOT)), 'review_sha256': hashlib.sha256(review_path.read_bytes()).hexdigest(),
        'job_error': case['job'].get('error')})
report.update(published_lessons=sum(bool(c['published_questions']) for c in report['cases']),
              published_questions=sum(kinds.values()), published_kind_counts=dict(kinds),
              published_review=dict(published_status), unpublished_partial_review=dict(partial_status),
              missing_published_target_reasons=dict(uncreated), all_cases_reviewed=True,
              all_chapters_complete=all(c['chapter_complete'] for c in report['cases']))
assert sum(uncreated.values()) + report['published_questions'] == 48
report['before'] = {'run_id': 'dev-v4-chapter', 'published_lessons': 5, 'published_questions': 30,
                    'limit': 'Different generated outputs; not a same-question causal accuracy comparison.'}
path = HERE / 'results/dev-v5-summary.json'
with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644), 'w') as f:
    json.dump(report, f, ensure_ascii=False, indent=2); f.write('\n')
print(json.dumps({k: report[k] for k in ('published_lessons', 'published_questions', 'published_review', 'missing_published_target_reasons', 'all_chapters_complete', 'release_ready')}))
