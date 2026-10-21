"""Bounded provider qualification on self-authored sources and isolated profiles.

Gemma stays local. A fresh Gemini run requires an explicit external flag; neither
route enables billing, substitutes another model, or overwrites prior evidence.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import time
import uuid

import httpx

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('gemma_dev_probe',ROOT/'experiments/07-gemma-local/probe_models.py')
dev=importlib.util.module_from_spec(spec);spec.loader.exec_module(dev)
MODEL='local:gemma4:12b-mlx'


def call(client,method,path,body=None,**kw):
    response=client.request(method,'/api'+path,json=body,**kw)
    if response.is_error:raise RuntimeError(f'{method} {path}: {response.status_code} {response.text[:1000]}')
    return response.json()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--confirm-coin',action='store_true')
    parser.add_argument('--model-choice',choices=[MODEL,'local:qwen3.5:9b','gemini:gemini-2.5-flash'],default=MODEL)
    parser.add_argument('--allow-external',action='store_true')
    recovery=parser.add_mutually_exclusive_group()
    recovery.add_argument('--resume-existing',action='store_true')
    recovery.add_argument('--resume-question-schema',action='store_true')
    recovery.add_argument('--resume-minimal-contract',action='store_true')
    recovery.add_argument('--fresh-complete-contract',action='store_true')
    recovery.add_argument('--resume-source-order-key',action='store_true')
    args=parser.parse_args()
    selected_model=args.model_choice;external=selected_model.startswith('gemini:')
    trial_name={MODEL:'gemma','local:qwen3.5:9b':'qwen9b','gemini:gemini-2.5-flash':'gemini'}[selected_model]
    display_name={MODEL:'Gemma local','local:qwen3.5:9b':'Qwen9B local','gemini:gemini-2.5-flash':'Gemini'}[selected_model]
    if selected_model!=MODEL and not args.fresh_complete_contract:raise SystemExit('Only fresh qualification is supported for a different model; no request sent.')
    if external and (not args.allow_external or not args.fresh_complete_contract):
        raise SystemExit('Gemini qualification requires --allow-external and --fresh-complete-contract; no request sent.')
    if args.resume_question_schema or args.resume_minimal_contract or args.resume_source_order_key:args.resume_existing=True
    if not args.confirm_coin:raise SystemExit('Pass --confirm-coin for this bounded QA trial; no request sent.')
    initial_path=ROOT/('backend/evidence/gemma-complete-contract-trial.json' if args.resume_source_order_key else 'backend/evidence/gemma-question-schema-recovery.json' if args.resume_minimal_contract else 'backend/evidence/gemma-pipeline-explicit-recovery.json' if args.resume_question_schema else 'backend/evidence/gemma-pipeline-live-trial.json')
    path=ROOT/('backend/evidence/gemma-source-order-key-recovery.json' if args.resume_source_order_key else f'backend/evidence/{trial_name}-complete-contract-trial.json' if args.fresh_complete_contract else 'backend/evidence/gemma-minimal-contract-recovery.json' if args.resume_minimal_contract else 'backend/evidence/gemma-question-schema-recovery.json' if args.resume_question_schema else 'backend/evidence/gemma-pipeline-explicit-recovery.json' if args.resume_existing else 'backend/evidence/gemma-pipeline-live-trial.json')
    if path.exists():raise SystemExit('Evidence already exists; keep the previous attempt. --resume-existing is limited to one explicit recovery.')
    report={'purpose':'Gemma12B MLX local backend pipeline on self-authored source; not Huy performance or held-out quality',
            'model':selected_model,'passed':False,'external_ai':external,'confirmed_proposed_app_coin':0,'monetary_payments':0,'runs':[],'errors':[]}
    if args.fresh_complete_contract:report['purpose']=f'One fresh {display_name} development pipeline after per-kind output and numbered-action source gate fixes; earlier Gemma four-question result remains unchanged. Not a held-out speed/quality benchmark.'
    def save():path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    def start(client,route,body):
        identity=uuid.uuid4().hex;headers={'Idempotency-Key':identity}
        response=client.post('/api'+route,json=body,headers=headers)
        if response.status_code==402:
            quote=response.json()['detail']
            if report['confirmed_proposed_app_coin']+quote['amount']>8:raise RuntimeError('QA cap8 proposed app Coin reached; no confirmation sent')
            if quote['model']!=selected_model.split(':',1)[1]:raise RuntimeError('Quote not pinned to the explicitly selected model')
            headers['Coin-Quote-Id']=quote['quote_id'];response=client.post('/api'+route,json=body,headers=headers)
            if response.is_success:report['confirmed_proposed_app_coin']+=quote['amount']
        response.raise_for_status();job_id=response.json()['job_id']
        run={'path':route,'job_id':job_id,'events':[]};report['runs'].append(run);save();begin=time.monotonic()
        for _ in range(1000):
            job=call(client,'GET','/jobs/'+job_id);p=job.get('progress') or {};preview=(p.get('preview') or {}).get('text','')
            event={'elapsed_seconds':round(time.monotonic()-begin,3),'status':job['status'],'phase':p.get('phase'),'saved_stages':p.get('saved_stages'),'preview_chars':len(preview)}
            if not run['events'] or event['status']!=run['events'][-1]['status'] or event['saved_stages']!=run['events'][-1]['saved_stages'] or bool(preview)!=bool(run['events'][-1]['preview_chars']):run['events'].append(event);save()
            if preview and run.get('first_visible_seconds') is None:run['first_visible_seconds']=event['elapsed_seconds']
            if job['status'] not in {'queued','running'}:
                run.update(status=job['status'],completed_seconds=event['elapsed_seconds'],provider=job['provider'],progress=p,error=job.get('error'),partial=job.get('partial'))
                save();return job
            if time.monotonic()-begin>230:
                run['observation_timeout']=True;save();raise TimeoutError('Observation expired; inspect the same saved job before retrying/restarting.')
            time.sleep(.25)
        raise TimeoutError('Polling cap; existing job remains identifiable in report.')
    try:
        with httpx.Client(base_url='http://127.0.0.1:8770',timeout=30,trust_env=False) as client:
            resume_id=None
            if args.resume_existing:
                prior=json.loads(initial_path.read_text())
                if prior['passed'] or len(prior['runs'])!=1:raise RuntimeError('Only the initial failed generation is eligible for this single explicit recovery.')
                client.cookies.update(json.loads((ROOT/('backend/runtime/gemma-complete-qa-session.json' if args.resume_source_order_key else 'backend/runtime/gemma-local-qa-session.json')).read_text()))
                catalog=call(client,'GET','/ai/models')
                if catalog['selected_model_id']!=selected_model:raise RuntimeError('Keep the originally selected Gemma; no model substitution during recovery.')
                report.update(source_id=prior['source_id'],source_revision=prior['source_revision'],course_id=prior['course_id'],
                              global_default_before=catalog['default_model_id'],selection=prior['selection'],resumed_from=prior['runs'][0]['job_id'])
                cid=prior['course_id'];resume_id=prior['runs'][0]['job_id'] if (prior['runs'][0].get('partial') or {}).get('reading') else None
                report['recovery_mode']='reuse_valid_reading' if resume_id else 'new_job_same_course_no_valid_reading'
                if args.resume_question_schema:report['recovery_reason']='Generation schema now expresses existing per-kind constraints; preserve reading/MCQ and try missing stages once.'
                if args.resume_minimal_contract:report['recovery_reason']='Model contract now requests only relevant per-kind fields and prompt no longer asks for choice/matching containers on typed questions. Reuse old validated stages and try missing stages once; never drop generated fields to accept them.'
                if args.resume_source_order_key:report['recovery_reason']='Ordering output no longer asks the model for an answer key. Derive it only from uniquely matched numbered source phrases; preserve four validated stages and their provenance, then create the two missing stages once.'
                current=call(client,'GET','/courses/'+cid)
                if current['revision']!=1:raise RuntimeError('Course changed; preserve it instead of replaying generation.')
                source=call(client,'GET','/sources/'+prior['source_id'])
                if source['revision']!=prior['source_revision']:raise RuntimeError('Source changed; no replay.')
            else:
                profile=call(client,'POST','/session');cookie=ROOT/(f'backend/runtime/{trial_name}-complete-qa-session.json' if args.fresh_complete_contract else 'backend/runtime/gemma-local-qa-session.json')
                cookie.write_text(json.dumps(dict(client.cookies)));cookie.chmod(0o600)
                catalog=call(client,'GET','/ai/models');report['global_default_before']=catalog['default_model_id']
                selected=call(client,'PUT','/ai/selection',{'model_id':selected_model,'expected_revision':catalog['selection_revision'],'allow_external':external})
                report['selection']=selected
                source=call(client,'POST','/sources/text',{'name':f'QA {display_name} — IPv4 /26','text':dev.NET})
                source=call(client,'POST','/sources/'+source['id']+'/review',{'expected_revision':source['revision'],'texts':[f['text'] for f in source['fragments']]})
                report['source_id']=source['id'];report['source_revision']=source['revision']
                plan=call(client,'POST','/plans/from-source-sections',{'source_id':source['id'],'expected_extraction_revision':source['revision'],
                            'subject':'Mạng máy tính','goal':'Hiểu IPv4, tính /26 và giải thích quy trình subnet từ nguồn',
                            'language':'vi','initial_mode':'learn','fragment_ids':[f['id'] for f in source['fragments']],
                            'question_types':['mcq','cloze','matching','ordering','short_answer'],'question_count':5,'card_count':2,'unlock_policy':'open'})
                outline={'title':f'QA {display_name} — IPv4 /26','units':[{'title':'IPv4 và subnet /26','objective':'Hiểu địa chỉ32 bit, dải subnet /26 và năm bước tính theo nguồn','source_refs':[f['id'] for f in source['fragments']]}]}
                plan=call(client,'PUT','/plans/'+plan['id'],{'expected_version':plan['outline']['version'],'outline':outline})
                approved=call(client,'POST','/plans/'+plan['id']+'/approve',{'expected_revision':plan['outline']['version']});cid=approved['course_id'];report['course_id']=cid;save()
            job=start(client,'/courses/'+cid+'/generate',{'unit_id':'unit-1','expected_revision':1,**({'resume_job_id':resume_id} if resume_id else {})})
            if job['status']!='succeeded':raise RuntimeError('Generation failed; partial stages retained, no automatic semantic retry.')
            editor=call(client,'GET','/courses/'+cid+'/editor');lesson=editor['content']['units'][0]['data']
            report['lesson']=lesson
            report['question_coverage']=editor['content']['units'][0].get('generation',{}).get('question_coverage')
            if len(lesson['questions'])!=5 or len(lesson['cards'])!=2 or set(q['kind'] for q in lesson['questions'])!={'mcq','cloze','matching','ordering','short_answer'}:
                raise RuntimeError('Qualification incomplete: requested five kinds/two cards; actual kinds='+','.join(q['kind'] for q in lesson['questions'])+'. Keep the recorded decline/partial; do not silently call this a pass.')
            answer_by_prompt={q['prompt']:q['answer'] for q in lesson['questions']}
            attempt=call(client,'POST','/courses/'+cid+'/sessions',{'expected_revision':editor['revision'],'unit_id':'unit-1','mode':'practice'})
            answers=[]
            for q in attempt['questions']:
                answers.append(call(client,'POST','/sessions/'+attempt['id']+'/answers',{'item_id':q['id'],'answer':answer_by_prompt[q['prompt']]}))
            report['deterministic_roundtrip']={'note':'Submitting generated reference keys tests grading/storage, NOT question correctness or Huy knowledge','answers':answers,
                                              'completion':call(client,'POST','/sessions/'+attempt['id']+'/complete')}
            chat=start(client,'/courses/'+cid+'/chat',{'unit_id':'unit-1','message':'Với ví dụ192.168.1.70/26 trong nguồn, vì sao có64 địa chỉ nhưng chỉ62 host dùng được? Trả ngắn gọn.'})
            assert chat['status']=='succeeded';report['chat']=chat['result']
            current=call(client,'GET','/ai/models');assert current['default_model_id']==report['global_default_before'] and current['selected_model_id']==selected_model
            report.update(passed=True,global_default_after=current['default_model_id'],external_ai_calls=sum(len(r.get('progress',{}).get('requests',[])) for r in report['runs']) if external else 0)
    except Exception as exc:
        report['errors'].append({'type':type(exc).__name__,'message':str(exc)[:1800]});raise
    finally:save();print(json.dumps({'passed':report['passed'],'evidence':str(path.relative_to(ROOT))}),flush=True)


if __name__=='__main__':main()
