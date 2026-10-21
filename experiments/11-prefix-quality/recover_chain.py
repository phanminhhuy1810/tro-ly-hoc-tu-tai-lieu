"""One explicit QA completion of ordering wrongly gated by function argument(0).

The measured dev-v4 snapshot remains unchanged. This is a separate post-fix
diagnostic; no full-lesson regeneration or failed semantic retries.
"""
import copy
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

import httpx

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from study_backend.extract import explicit_sequence
from study_backend.ordering import derive_generated_ordering

HERE=Path(__file__).resolve().parent
out=HERE/'results/chain-ordering-recovery.json'
if out.exists():raise SystemExit('Recovery evidence exists; inspect saved IDs, do not repeat generation.')
raw_path=ROOT/'experiments/08-quality-evaluation/results/dev-v4-chapter.json';raw=raw_path.read_bytes();run=json.loads(raw)
assert run['all_cases_observed']
case=next(x for x in run['runs'] if x['case_id']=='calc-dev-chain')
cid,uid=case['course_id'],case['unit_id'];source=case['source_snapshot']['fragments']
before=case['course_snapshot'];old_unit=before['content']['units'][0]
assert any(x['stage']=='ordering' and x['origin']=='backend_source_gate' for x in old_unit['generation']['question_coverage']['uncreated'])
assert explicit_sequence(source)
steps=[f for f in source if f['text'].startswith(('1. ','2. ','3. ','4. '))]
replay={'kind':'ordering','options':[f['text'].split('. ',1)[1] for f in reversed(steps)],'source_refs':[f['id'] for f in steps]}
derived,_=derive_generated_ordering(replay,source)
assert derived['answer']==[3,2,1,0] and derived['source_refs']==replay['source_refs']
report={'purpose':'Separate post-fix ordering completion on the original dev-v4 QA course; measured run is not overwritten or counted again.',
        'at':datetime.now(timezone.utc).isoformat(),'course_id':cid,'unit_id':uid,'case_id':case['case_id'],
        'dev_raw_sha256':hashlib.sha256(raw).hexdigest(),'before_source_gate':'backend_source_gate rejected ordering in v23',
        'same_source_after_gate':True,'same_source_replay_key':derived['answer'],'same_source_replay_inference_calls':0,
        'limits':{'completion_jobs':1,'seconds':210,'semantic_retries':0},'external_inference':0,'payments':0,
        'independent_human_reviews':0,'checks':{}}
def save():out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
with httpx.Client(base_url='http://127.0.0.1:8770/api',trust_env=False,timeout=25,
                  cookies=json.loads((ROOT/'backend/runtime/quality-evaluation/dev-v4-chapter/calc-dev-chain.json').read_text())) as client:
    def call(method,path,body=None,headers=None):
        r=client.request(method,path,json=body,headers=headers);r.raise_for_status();return r.json()
    current=call('GET','/courses/'+cid+'/editor')
    assert current['revision']==before['revision'] and current['content']['units'][0]['data']==old_unit['data']
    report['completion_before']=call('GET','/courses/'+cid+'/question-completion?unit_id='+uid)
    chapter=call('GET','/courses/'+cid+'/chapter-context?unit_id='+uid);assert chapter['complete']
    with sqlite3.connect('file:'+str(ROOT/'backend/runtime/study.sqlite3')+'?mode=ro',uri=True) as db:
        nodes=db.execute('SELECT nodes_json FROM chapter_contexts WHERE id=?',(chapter['context_id'],)).fetchone()[0]
    old_session=call('GET','/sessions/'+case['session_id'])
    wallet=call('GET','/wallet');report['wallet_before']=wallet;save()
    body={'expected_revision':current['revision'],'unit_id':uid,'stages':['ordering']}
    headers={'Idempotency-Key':'chain-math-argument-source-gate-fix'}
    response=client.post('/courses/'+cid+'/question-completion',json=body,headers=headers)
    if response.status_code==402:
        quote=response.json()['detail'];assert quote['amount']<=4
        report['quote_amount']=quote['amount'];headers['Coin-Quote-Id']=quote['quote_id']
        response=client.post('/courses/'+cid+'/question-completion',json=body,headers=headers)
    response.raise_for_status();jid=response.json()['job_id'];report['job_id']=jid;save();began=time.monotonic()
    while True:
        job=call('GET','/jobs/'+jid)
        if job['status'] in {'succeeded','failed','cancelled'}:break
        if time.monotonic()-began>205:call('POST','/jobs/'+jid+'/cancel');break
        time.sleep(.6)
    job=call('GET','/jobs/'+jid);report['job']=job;report['status']=job['status'];report['elapsed_seconds']=round(time.monotonic()-began,3)
    after=call('GET','/courses/'+cid+'/editor')
    report['checks']['old_lesson_not_regenerated']=after['revision']==current['revision'] and after['content']['units'][0]['data']==old_unit['data']
    if job['status']=='succeeded' and (job.get('result') or {}).get('proposal_id'):
        pid=job['result']['proposal_id'];preview=call('GET','/proposals/'+pid);report['preview']=preview;save()
        questions=preview['after']['questions'];assert questions[:-1]==old_unit['data']['questions']
        question=questions[-1];assert question['kind']=='ordering' and question['source_refs']
        report['checks']['preview_appends_exactly_one_ordering']=len(questions)==len(old_unit['data']['questions'])+1
        call('POST','/proposals/'+pid+'/apply',{'expected_revision':current['revision']})
        applied=call('GET','/courses/'+cid+'/editor');report['applied_revision']=applied['revision']
        new_unit=applied['content']['units'][0]
        report['checks']['old_questions_and_reading_unchanged']=all(new_unit['data'][k]==old_unit['data'][k] for k in ['title','sections','cards','mindmap']) and new_unit['data']['questions'][:-1]==old_unit['data']['questions']
        report['checks']['old_attempt_snapshot_preserved']=call('GET','/sessions/'+case['session_id'])==old_session
    with sqlite3.connect('file:'+str(ROOT/'backend/runtime/study.sqlite3')+'?mode=ro',uri=True) as db:
        report['checks']['chapter_not_read_again']=db.execute('SELECT nodes_json FROM chapter_contexts WHERE id=?',(chapter['context_id'],)).fetchone()[0]==nodes and not any(r['schema']=='ChapterBrief' for r in job['progress']['requests'])
    report['checks']['source_unchanged']=call('GET','/sources/'+case['source_id'])==case['source_snapshot']
    report['checks']['original_measurement_retained']=raw_path.read_bytes()==raw
    report['wallet_after']=call('GET','/wallet');report['completed_at']=datetime.now(timezone.utc).isoformat();save()
print(json.dumps({'status':report['status'],'seconds':report['elapsed_seconds'],'applied_revision':report.get('applied_revision'),'checks':report['checks']}),flush=True)
if report['status']!='succeeded' or not report.get('applied_revision'):
    raise SystemExit('Retained unsuccessful completion; no automatic retry.')
assert all(report['checks'].values()),report['checks']
