"""One paired development preview after changing correction inputs.

Same source, request, question and local model as the retained v3 failure.
No auto-apply, semantic retry, final-set access or default selection change.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

import httpx

ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'backend'))
from study_backend.correction_context import CORRECTION_PROMPT_VERSION
from study_backend.correction_prompt import INPUT_STRATEGY

OUT=HERE/'results/operant-correction-inputs-v4.json'
assert not OUT.exists(),'Keep the existing run; observe its recorded job ID instead of submitting again.'
base_path=HERE/'results/operant-correction-preview.json';raw=base_path.read_bytes();base=json.loads(raw)
assert base['source_review']['status']=='reject_do_not_apply'
evaluation_path=ROOT/'experiments/08-quality-evaluation/results/dev-v5-chapter-focus.json'
evaluation=evaluation_path.read_bytes();case=next(c for c in json.loads(evaluation)['runs'] if c['case_id']=='psy-dev-operant')
cid=case['course_id'];body=base['request'];db_path=ROOT/'backend/runtime/study.sqlite3'
with sqlite3.connect('file:'+str(db_path)+'?mode=ro',uri=True) as db:
    assert not db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running')").fetchone()
    assert db.execute('SELECT model_id FROM ai_preferences WHERE owner_id=?',(case['qa_owner_id'],)).fetchone()[0]=='local:gemma4:12b-mlx'
source_files=sorted((ROOT/'backend/study_backend').glob('*.py'))
production_hash=hashlib.sha256(b''.join(p.name.encode()+b'\0'+p.read_bytes()+b'\0' for p in source_files)).hexdigest()
report={'purpose':'Single paired development preview; a Codex source review is not an independent human/factual accuracy score.',
        'at':datetime.now(timezone.utc).isoformat(),'case_id':case['case_id'],'course_id':cid,'request':body,
        'baseline_sha256':hashlib.sha256(raw).hexdigest(),'dev_raw_sha256':hashlib.sha256(evaluation).hexdigest(),
        'production_sha256':production_hash,'protocol_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'expected_prompt_version':CORRECTION_PROMPT_VERSION,'expected_input_strategy':INPUT_STRATEGY,
        'limits':{'correction_jobs':1,'seconds':210},'external_inference':0,'automatic_semantic_retries':0,
        'independent_human_reviews':0,'model_quality_pass':None,'checks':{}}
def save():OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
cookie=ROOT/'backend/runtime/quality-evaluation/dev-v5-chapter-focus/psy-dev-operant.json'
with httpx.Client(base_url='http://127.0.0.1:8770/api',trust_env=False,timeout=20,cookies=json.loads(cookie.read_text())) as client:
    def call(method,path,body=None,headers=None):
        r=client.request(method,path,json=body,headers=headers);r.raise_for_status();return r.json()
    before=call('GET','/courses/'+cid+'/editor');question=before['content']['units'][0]['data']['questions'][body['index']]
    assert before['revision']==body['expected_revision'] and question==base['before_question']
    chapter=call('GET','/courses/'+cid+'/chapter-context?unit_id='+body['unit_id']);assert chapter==base['chapter_before']
    with sqlite3.connect('file:'+str(db_path)+'?mode=ro',uri=True) as db:
        nodes=db.execute('SELECT nodes_json FROM chapter_contexts WHERE id=?',(chapter['context_id'],)).fetchone()[0]
    session=call('GET','/sessions/'+case['session_id']);old_job=call('GET','/jobs/'+case['job_id'])
    baseline_job=call('GET','/jobs/'+base['job_id']);assert baseline_job==base['job']
    report.update(before_question=question,chapter_before=chapter,wallet_before=call('GET','/wallet'));save()
    headers={'Idempotency-Key':'operant-correction-inputs-v4-once'}
    response=client.post('/courses/'+cid+'/proposals',json=body,headers=headers)
    if response.status_code==402:
        quote=response.json()['detail'];assert quote['amount']<=2 and quote['model']=='gemma4:12b-mlx'
        report['quote_amount']=quote['amount'];headers['Coin-Quote-Id']=quote['quote_id']
        response=client.post('/courses/'+cid+'/proposals',json=body,headers=headers)
    response.raise_for_status();jid=response.json()['job_id'];report['job_id']=jid;save();start=time.monotonic()
    print(json.dumps({'job_id':jid,'status':'started'}),flush=True)
    while True:
        job=call('GET','/jobs/'+jid)
        if job['status'] in {'succeeded','failed','cancelled'}:break
        if time.monotonic()-start>205:
            call('POST','/jobs/'+jid+'/cancel');job=call('GET','/jobs/'+jid);break
        time.sleep(.5)
    report.update(job=job,status=job['status'],elapsed_seconds=round(time.monotonic()-start,3))
    checks=report['checks'];checks['expected_prompt_recorded']=job['provider']['prompt_version']==CORRECTION_PROMPT_VERSION
    checks['question_input_strategy_recorded']=job['partial'].get('replacement_input_strategy')==INPUT_STRATEGY
    checks['course_unchanged_before_apply']=call('GET','/courses/'+cid+'/editor')==before
    if job['status']=='succeeded' and (job.get('result') or {}).get('proposal_id'):
        preview=call('GET','/proposals/'+job['result']['proposal_id']);report['preview']=preview
        checks['only_selected_question_preview']=preview['scope']=={'unit_id':body['unit_id'],'target':'question','index':body['index']}
        checks['stem_kept_exactly']=preview['after']['prompt']==question['prompt']
        checks['kind_kept']=preview['after']['kind']==question['kind']
        checks['creator_metadata_kept']=all(preview['after'].get(k)==question.get(k) for k in ('difficulty','difficulty_basis'))
    checks['old_attempt_unchanged']=call('GET','/sessions/'+case['session_id'])==session
    checks['original_job_unchanged']=call('GET','/jobs/'+case['job_id'])==old_job
    checks['baseline_job_unchanged']=call('GET','/jobs/'+base['job_id'])==baseline_job
    checks['source_unchanged']=call('GET','/sources/'+case['source_id'])==case['source_snapshot']
    checks['original_measurement_retained']=evaluation_path.read_bytes()==evaluation
    checks['baseline_retained']=base_path.read_bytes()==raw
    checks['one_short_answer_request']=[r['schema'] for r in job['progress']['requests']]==['ShortAnswerDraft']
    with sqlite3.connect('file:'+str(db_path)+'?mode=ro',uri=True) as db:
        checks['chapter_cache_unchanged']=nodes==db.execute('SELECT nodes_json FROM chapter_contexts WHERE id=?',(chapter['context_id'],)).fetchone()[0]
    report['wallet_after']=call('GET','/wallet');checks['no_coin_held']=report['wallet_after']['held']==0;save()
print(json.dumps({'status':report['status'],'seconds':report['elapsed_seconds'],'checks':report['checks']}),flush=True)
