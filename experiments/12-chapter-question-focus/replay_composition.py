"""Replay the exact saved ambiguous MCQ, with no model call or DB write."""
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from study_backend.polynomial_questions import composition_proof, verify_composition, CompositionError
from study_backend.generation_contract import GENERATION_PROCESSOR_VERSION

run = json.loads((ROOT / 'experiments/08-quality-evaluation/results/dev-v5-chapter-focus.json').read_text())
case = next(c for c in run['runs'] if c['case_id'] == 'calc-dev-chain')
assert case['job']['status'] == 'failed' and not case['published_question_count']
q = case['job']['partial']['questions']['mcq']['question']; before = copy.deepcopy(q)
assert case['job']['provider']['processor_version'] == '20261021-math-argument-step-boundary-v12'
assert next(r for r in case['job']['progress']['requests'] if r['schema'] == 'McqDraft')['phase'] == 'received'
try: verify_composition(q)
except CompositionError as exc: issue = {'code': exc.code, 'reason': str(exc), 'proof': exc.proof}
else: raise AssertionError('The retained ambiguous candidate was accepted.')
assert q == before and issue['proof']['valid_option_indices'] == [0, 2]
positive = copy.deepcopy(q)
positive['options'][2] = 'Hàm trong là g(x)=3x+2, hàm ngoài là f(u)=u^4'
verify_composition(positive)
report = {'purpose': 'Same saved MCQ checked with an exact bounded polynomial guard, not a regenerated or repaired model answer.',
          'at': datetime.now(timezone.utc).isoformat(), 'question': q,
          'question_sha256': hashlib.sha256(json.dumps(q, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
          'before': {'state': 'validated_checkpoint_not_published', 'processor_version': case['job']['provider']['processor_version']},
          'after': {'processor_version': GENERATION_PROCESSOR_VERSION, 'rejection': issue},
          'original_unchanged': q == before, 'inference_calls': 0, 'database_writes': 0,
          'manual_positive_comparison': 'A separately labelled altered distractor gives one valid composition; it never replaces the saved model output.',
          'limit': 'Only the explicit bounded polynomial grammar; unknown domains/functions/wording remain unproved and need review.'}
path = HERE / 'results/same-question-composition.json'
with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644), 'w') as f:
    json.dump(report, f, ensure_ascii=False, indent=2); f.write('\n')
print(json.dumps({'valid_choices': issue['proof']['valid_option_indices'], 'rejected': True, 'raw_unchanged': True, 'inference_calls': 0}))
