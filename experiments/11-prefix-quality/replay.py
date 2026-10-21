"""Same saved model question, new guard; no inference, key repair or DB edit."""
import copy
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from study_backend.subnet_reasoning import check_question,SubnetClaimError,calculations
from study_backend.generation_contract import GENERATION_PROCESSOR_VERSION

here=Path(__file__).resolve().parent;path=here/'results/same-question-bit-claim.json'
if path.exists():raise SystemExit('Replay evidence exists; do not overwrite it.')
path.parent.mkdir(parents=True,exist_ok=True)
trial=json.loads((ROOT/'experiments/10-source-support/results/network-local-v22-resume.json').read_text())
unit=next(u for u in trial['course_snapshot']['content']['units'] if u['id']==trial['unit_id'])
q=next(q for q in unit['data']['questions'] if q['kind']=='mcq');before=copy.deepcopy(q)
assert trial['job']['status']=='succeeded' and trial['job']['provider']['processor_version']=='20261021-chapter-subnet-claims-v10'
try:check_question(q)
except SubnetClaimError as exc:rejection={'code':exc.code,'message':str(exc)}
else:raise AssertionError('The retained contradictory bit decomposition was accepted.')
assert q==before
positive=copy.deepcopy(q);positive['explanation']=positive['explanation'].replace('2 octet đầu và 1 bit','2 octet đầu và 3 bit')
check_question(positive)
for other in unit['data']['questions']:
    if other['kind']!='mcq':check_question(other)
report={'purpose':'Replay the exact published v22 model MCQ through a revised numeric guard. No model regeneration or retrospective raw-output repair.',
 'at':datetime.now(timezone.utc).isoformat(),'inference_calls':0,'database_writes':0,
 'input_question':q,'input_sha256':hashlib.sha256(json.dumps(q,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),
 'before':{'processor_version':trial['job']['provider']['processor_version'],'published_in_course_revision':trial['course_snapshot']['revision'],
           'evidence':'Historical v22 HTTP trial and retained raw question; the old pipeline accepted it.'},
 'after':{'processor_version':GENERATION_PROCESSOR_VERSION,'rejection':rejection,'question_unchanged':q==before},
 'manual_positive_comparison':'The independently labeled three-bit correction passes; it is not substituted for the original model question.',
 'other_saved_questions_accepted':2,'oracle':calculations('172.100.112.4/19')[0],
 'limit':'Narrow IPv4 arithmetic guard, not general semantic validation or a factual-accuracy score for all model answers.'}
path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'same_question_rejected':True,'raw_unchanged':True,'other_questions_accepted':2,'inference_calls':0}))
