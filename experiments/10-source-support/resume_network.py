"""One explicit post-fix QA continuation of the retained v21 failure.

Uses the same reviewed source/plan and cached complete chapter. No regeneration
loop, changed model, replacement content, or new profile/source is hidden here.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import time

import httpx

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
output=HERE/'results/network-local-v22-resume.json'
if output.exists():raise SystemExit('Continuation exists; inspect its saved job instead of retrying.')
previous=json.loads((ROOT/'experiments/09-chapter-first/results/network-local-v3-support.json').read_text())
assert previous['status']=='failed'
failed=previous['jobs'][-1]['job']
assert failed['status']=='failed' and failed['partial']['chapter_context']['complete']
report={'purpose':'One explicit local QA continuation after the missing mindmap-source field prompt fix; same chapter cache/source/goal/model.',
        'started_at':datetime.now(timezone.utc).isoformat(),'previous_failed_job_id':failed['id'],
        'course_id':previous['course_id'],'unit_id':previous['unit_id'],'source_id':previous['source_id'],
        'qa_owner_id':previous['qa_owner_id'],'model':previous['model'],
        'limits':{'requests_to_generate':1,'poll_seconds':210,'automatic_failure_retries':0},
        'external_inference':0,'payments':0,'independent_human_reviewed':False}
def save():output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
with httpx.Client(base_url='http://127.0.0.1:8770',timeout=30,trust_env=False,
                  cookies=json.loads((ROOT/'backend/runtime/chapter-first/network-local-v3-support.json').read_text())) as client:
    def call(method,path,body=None,headers=None):
        response=client.request(method,'/api'+path,json=body,headers=headers);response.raise_for_status();return response.json()
    cid=report['course_id'];uid=report['unit_id']
    course=call('GET','/courses/'+cid+'/editor');report['before_revision']=course['revision']
    chapter_before=call('GET','/courses/'+cid+'/chapter-context?unit_id='+uid)
    assert chapter_before['complete']
    source=call('GET','/sources/'+report['source_id']);report['source_sha256']=hashlib.sha256(json.dumps(source['fragments'],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    with sqlite3.connect('file:'+str(ROOT/'backend/runtime/study.sqlite3')+'?mode=ro',uri=True) as db:
        nodes_before=db.execute('SELECT nodes_json FROM chapter_contexts WHERE id=?',(chapter_before['context_id'],)).fetchone()[0]
    report['wallet_before']=call('GET','/wallet');report['default_model_before']=call('GET','/ai/models')['default_model_id'];save()
    began=time.monotonic();body={'expected_revision':course['revision'],'unit_id':uid,'resume_job_id':failed['id']}
    headers={'Idempotency-Key':'chapter-support-v22-explicit-resume'}
    response=client.post('/api/courses/'+cid+'/generate',json=body,headers=headers)
    if response.status_code==402:
        quote=response.json()['detail'];assert quote['amount']<=8
        headers['Coin-Quote-Id']=quote['quote_id'];response=client.post('/api/courses/'+cid+'/generate',json=body,headers=headers)
    response.raise_for_status();jid=response.json()['job_id'];report['job_id']=jid;save()
    while True:
        job=call('GET','/jobs/'+jid)
        if job['status'] in {'succeeded','failed','cancelled'}:break
        if time.monotonic()-began>205:
            call('POST','/jobs/'+jid+'/cancel');break
        time.sleep(.8)
    report['job']=call('GET','/jobs/'+jid);report['status']=report['job']['status']
    report['elapsed_seconds']=round(time.monotonic()-began,3)
    report['course_snapshot']=call('GET','/courses/'+cid+'/editor')
    report['chapter_context']=call('GET','/courses/'+cid+'/chapter-context?unit_id='+uid)
    with sqlite3.connect('file:'+str(ROOT/'backend/runtime/study.sqlite3')+'?mode=ro',uri=True) as db:
        row=db.execute('SELECT manifest_json,nodes_json FROM chapter_contexts WHERE id=?',(chapter_before['context_id'],)).fetchone()
    report['context_manifest']=json.loads(row[0]);report['context_nodes']=json.loads(row[1])
    report['checks']={'same_complete_chapter':report['chapter_context']['context_id']==chapter_before['context_id'] and report['chapter_context']['complete'],
        'no_chapter_reread':row[1]==nodes_before and not any(x['schema']=='ChapterBrief' for x in report['job']['progress']['requests']),
        'source_unchanged':source==call('GET','/sources/'+report['source_id']),
        'old_failed_partial_unchanged':call('GET','/jobs/'+failed['id'])['partial']==failed['partial']}
    report['wallet_after']=call('GET','/wallet');report['default_model_after']=call('GET','/ai/models')['default_model_id']
    report['checks']['default_model_unchanged']=report['default_model_before']==report['default_model_after']
    report['finished_at']=datetime.now(timezone.utc).isoformat();save()
print(json.dumps({'status':report['status'],'elapsed_seconds':report['elapsed_seconds'],'checks':report['checks']}),flush=True)
if report['status']!='succeeded':raise SystemExit('Retained failed continuation; no further automatic generation.')
