"""Bounded local inference over frozen notes, using production HTTP endpoints.

One generation per case. Failed/declined/partial outputs remain in the report.
--observe resumes observation of an existing run, never failed generation.
Session cookies stay in private runtime files and never in the result bundle.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

import httpx

from oracles import verify_facts

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
BASE='http://127.0.0.1:8770'
TERMINAL={'succeeded','failed','cancelled'}
MODEL='local:gemma4:12b-mlx'


def now():return datetime.now(timezone.utc).isoformat()


def fingerprint():
    files=sorted((ROOT/'backend/study_backend').glob('*.py'))
    return hashlib.sha256(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files},sort_keys=True).encode()).hexdigest()


def protocol_fingerprint():
    return hashlib.sha256(json.dumps({name:hashlib.sha256((HERE/name).read_bytes()).hexdigest()
        for name in ['run_http.py','oracles.py']},sort_keys=True).encode()).hexdigest()


def check_free(own_ids):
    with sqlite3.connect('file:'+str(ROOT/'backend/runtime/study.sqlite3')+'?mode=ro',uri=True) as db:
        rows=db.execute("SELECT id FROM jobs WHERE status IN ('queued','running') AND task!='source_ocr'").fetchall()
    if any(row[0] not in own_ids for row in rows):
        raise RuntimeError('Another app AI job is active. No new evaluation job will be submitted; inspect saved live IDs.')


def request(client,method,path,body=None,headers=None):
    response=client.request(method,'/api'+path,json=body,headers=headers)
    response.raise_for_status();return response.json()


def load_frozen(split):
    freeze=json.loads((HERE/'freeze.json').read_text())
    raw=(HERE/(split+'.json')).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=freeze['split_hashes'][split+'.json']:
        raise ValueError('Frozen split changed; no model call.')
    cases=json.loads(raw)['cases']
    if len(cases)!=6 or any(c['split']!=split for c in cases):raise ValueError('Invalid split')
    for case in cases:verify_facts(case['expected_facts'])
    return freeze,cases


def capture_outcome(client,item,job):
    item['job']=job;item['finished_observing_at']=now()
    cid=item['course_id']
    course=request(client,'GET','/courses/'+cid+'/editor')
    item['course_snapshot']=course
    unit=course['content']['units'][0];data=unit.get('data')
    item['published_question_count']=len(data.get('questions',[])) if data else 0
    item['published_kinds']=[q['kind'] for q in data.get('questions',[])] if data else []
    continuation=bool((job.get('result') or {}).get('continuation_required'))
    if continuation and data:raise ValueError('Chapter continuation unexpectedly published a lesson; do not count or grade it.')
    item['outcome_kind']=('chapter_continuation_required' if continuation else 'published_lesson' if data else 'no_published_lesson')
    item['chapter_context']=(unit.get('generation') or {}).get('chapter_context') or job.get('partial',{}).get('chapter_context')
    item['evidence_scope']=(unit.get('generation') or {}).get('evidence_scope') or job.get('partial',{}).get('evidence_scope')
    item['ai_request_schemas']=[r['schema'] for r in (job.get('progress') or {}).get('requests',[])]
    item['wallet_after']=request(client,'GET','/wallet')
    if data:
        # This checks HTTP persistence/grade, NOT whether the generated key is correct.
        session=(request(client,'GET','/sessions/'+item['session_id']) if item.get('session_id') else
                 request(client,'POST','/courses/'+cid+'/sessions',{'expected_revision':course['revision'],'unit_id':item['unit_id']},
                         headers={'Idempotency-Key':'quality-roundtrip-'+item['case_id']}))
        item['session_id']=session['id'];graded=[]
        for q in session['questions']:
            matches=[v for v in data['questions'] if v['kind']==q['kind'] and v['prompt']==q['prompt']]
            if len(matches)!=1:raise ValueError('Session item does not uniquely match its pinned content; no answer submitted.')
            question=matches[0]
            value=request(client,'POST','/sessions/'+session['id']+'/answers',{'item_id':q['id'],'answer':question['answer']})
            graded.append({'kind':question['kind'],'result':value})
        item['key_roundtrip_grades']=graded
        item['completed_session']=request(client,'POST','/sessions/'+session['id']+'/complete')
        item['roundtrip_limit']='Submitted generated keys only to test deterministic grading/storage. These results are never factual-quality scores.'
    item['outcome_captured']=True


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--split',choices=['dev','final'],required=True)
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--observe',action='store_true')
    parser.add_argument('--max-seconds',type=int,default=1500)
    args=parser.parse_args()
    if not args.run_id.replace('-','').isalnum():raise SystemExit('Use a simple alphanumeric run ID.')
    if not 250<=args.max_seconds<=1800:raise SystemExit('Run bound must be250–1800seconds.')
    freeze,cases=load_frozen(args.split)
    release=fingerprint();protocol=protocol_fingerprint()
    if args.split=='final':
        marker=json.loads((HERE/'release.json').read_text())
        if marker['production_sha256']!=release or marker['split_hashes']!=freeze['split_hashes'] or marker.get('protocol_sha256')!=protocol:
            raise SystemExit('Final evaluation requires the frozen release and split hashes; no inference sent.')
    path=HERE/'results'/(args.run_id+'.json')
    private_dir=ROOT/'backend/runtime/quality-evaluation'/args.run_id
    private_dir.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if not args.observe:raise SystemExit('Run exists. Observe existing job IDs; never overwrite or regenerate failed cases.')
        report=json.loads(path.read_text())
        if report['production_sha256']!=release:raise SystemExit('Code changed after this run; keep evidence, create a separately labelled new run.')
        if report.get('protocol_sha256') and report['protocol_sha256']!=protocol:raise SystemExit('Evaluation harness changed; inspect saved job IDs without changing measurement rules.')
        if report['split']!=args.split:raise SystemExit('Split mismatch')
    else:
        if args.observe:raise SystemExit('No run exists to observe.')
        report={'purpose':'Frozen three-subject notes evaluation over local production HTTP; agent-authored sources and labels, not independent user/instructor review.',
                'split':args.split,'run_id':args.run_id,'started_at':now(),'model':MODEL,
                'production_sha256':release,'protocol_sha256':protocol,'protocol_version':'whole-chapter-observation-v2',
                'split_hashes':freeze['split_hashes'],'runs':[],
                'semantic_retries':0,'external_inference':0,'payments':0,
                'limits':{'cases':6,'questions_per_case':8,'job_observation_seconds':240,'wall_seconds':args.max_seconds,'proposed_qa_coin_per_case':10},
                'human_reviewed':False,'all_cases_observed':False}
    def save():path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    started=time.monotonic();save()
    try:
        for case in cases:
            item=next((r for r in report['runs'] if r['case_id']==case['id']),None)
            if item and item.get('job',{}).get('status') in TERMINAL and item.get('outcome_captured'):continue
            if time.monotonic()-started>args.max_seconds-250:
                report['deferred_reason']='Wall budget reached before starting another case.';break
            if fingerprint()!=release:raise RuntimeError('Production code changed mid-run; preserve current report, stop new calls.')
            check_free({r['job_id'] for r in report['runs'] if r.get('job_id')})
            with httpx.Client(base_url=BASE,timeout=30,trust_env=False) as client:
                cookie=private_dir/(case['id']+'.json')
                if item:
                    client.cookies.update(json.loads(cookie.read_text()))
                    if not item.get('job_id'):raise RuntimeError('Setup was interrupted; inspect saved IDs instead of creating a duplicate course.')
                else:
                    item={'case_id':case['id'],'subject':case['subject'],'started_at':now(),
                          'oracle':verify_facts(case['expected_facts']),'expected_source_ordering':case['expected_source_ordering'],
                          'source_sha256':hashlib.sha256(case['text'].encode()).hexdigest(),'events':[]}
                    report['runs'].append(item);save()
                    profile=request(client,'POST','/session');item['qa_owner_id']=profile['id']
                    cookie.touch(mode=0o600);cookie.write_text(json.dumps(dict(client.cookies))+'\n');cookie.chmod(0o600)
                    catalog=request(client,'GET','/ai/models')
                    item['default_model_before']=catalog['default_model_id']
                    item['selection']=request(client,'PUT','/ai/selection',{'model_id':MODEL,'expected_revision':catalog['selection_revision'],'allow_external':False})
                    source=request(client,'POST','/sources/text',{'name':'QA '+case['id']+' — '+case['title'],'text':case['text']})
                    item['source_id']=source['id'];save()
                    source=request(client,'POST','/sources/'+source['id']+'/review',{'expected_revision':source['revision'],'texts':[f['text'] for f in source['fragments']]})
                    prefs={key:case[key] for key in ['subject','goal','language','difficulty','question_types','question_count','card_count','terms_to_keep']}
                    plan=request(client,'POST','/plans/from-source-sections',{**prefs,'source_id':source['id'],'expected_extraction_revision':source['revision'],'fragment_ids':[f['id'] for f in source['fragments']]})
                    approved=request(client,'POST','/plans/'+plan['id']+'/approve',{'expected_revision':1})
                    item['course_id']=approved['course_id'];item['source_snapshot']=source
                    course=request(client,'GET','/courses/'+item['course_id']+'/editor')
                    if len(course['content']['units'])!=1:raise RuntimeError('Fixture no longer fits a single unit. Keep setup; do not silently narrow source scope.')
                    item['unit_id']=course['content']['units'][0]['id'];item['wallet_before']=request(client,'GET','/wallet');save()
                    identity='quality-'+args.run_id+'-'+case['id'];headers={'Idempotency-Key':identity}
                    body={'expected_revision':course['revision'],'unit_id':item['unit_id']}
                    route='/api/courses/'+item['course_id']+'/generate'
                    response=client.post(route,json=body,headers=headers)
                    if response.status_code==402:
                        quote=response.json()['detail'];item['quote']=quote;save()
                        if quote['amount']>10 or quote['model']!=MODEL.split(':',1)[1]:raise RuntimeError('QA quote cap/model mismatch; no confirmation sent.')
                        headers['Coin-Quote-Id']=quote['quote_id'];response=client.post(route,json=body,headers=headers)
                    response.raise_for_status();item['job_id']=response.json()['job_id'];save()
                    print(json.dumps({'case':case['id'],'job':item['job_id'],'status':'started'}),flush=True)
                began=time.monotonic()
                last_event=None
                while True:
                    job=request(client,'GET','/jobs/'+item['job_id']);p=job.get('progress') or {}
                    event={'status':job['status'],'phase':p.get('phase'),'saved_stages':p.get('saved_stages'),'planned_stages':p.get('planned_stages')}
                    if event!=last_event:
                        item['events'].append({**event,'observed_at':now()});last_event=event;save()
                        if job['status'] in TERMINAL or event['phase'] in ('validating','committing'):
                            print(json.dumps({'case':case['id'],**event}),flush=True)
                    if job['status'] in TERMINAL:
                        capture_outcome(client,item,job);save();break
                    if time.monotonic()-began>240:
                        item['observation_expired_at']=now();save()
                        raise TimeoutError('Observation expired; same job remains identified. Use --observe; do not restart or generate another job.')
                    time.sleep(.4)
        report['all_cases_observed']=len(report['runs'])==len(cases) and all(r.get('job',{}).get('status') in TERMINAL and r.get('outcome_captured') for r in report['runs'])
        report['finished_observing_at']=now()
    except Exception as exc:
        report.setdefault('harness_errors',[]).append({'at':now(),'type':type(exc).__name__,'message':str(exc)[:1200]})
        save();raise
    finally:save()
    print(json.dumps({'run':args.run_id,'all_cases_observed':report['all_cases_observed'],'statuses':{r['case_id']:r.get('job',{}).get('status','setup_or_live') for r in report['runs']}}),flush=True)


if __name__=='__main__':main()
