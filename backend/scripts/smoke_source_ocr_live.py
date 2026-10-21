"""Bounded localhost/native OCR development trial. No provider/model calls."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time

import httpx

ROOT=Path(__file__).resolve().parents[2]
RUNTIME=ROOT/'backend/runtime'
EVIDENCE=ROOT/'backend/evidence/source-ocr-live-trial.json'


def save(path,value,private=False):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    if private:os.chmod(path,0o600)


def request(client,method,path,**kwargs):
    response=client.request(method,path,**kwargs)
    if response.is_error:
        raise RuntimeError(f'{method} {path}: {response.status_code} {response.text[:500]}')
    return response.json()


def wait_job(client,job_id,timeout=65):
    deadline=time.monotonic()+timeout
    for _ in range(500):
        value=request(client,'GET','/api/jobs/'+job_id)
        if value['status'] not in {'queued','running'}:return value
        if time.monotonic()>deadline:break
        time.sleep(.15)
    raise TimeoutError('Observation deadline; server job has not been implicitly cancelled.')


def action(batch,revision=None):
    return {'expected_revision':batch['base_revision'] if revision is None else revision,
            'expected_batch_version':batch['version']}


def finish(client,source,keys=None):
    body={'expected_revision':source['revision']}
    if keys is not None:body['items']=keys
    start=request(client,'POST',f"/api/sources/{source['id']}/ocr-batches",json=body,
                  headers={'Idempotency-Key':os.urandom(12).hex()})
    job=wait_job(client,start['job_id']);assert job['status']=='succeeded',job
    batch=request(client,'GET','/api/ocr-batches/'+job['result']['ocr_batch_id'])
    assert not batch['remaining_count'],batch
    return batch,job


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--base',default='http://127.0.0.1:8770')
    args=parser.parse_args();data={'kind':'self_authored_development_native_ocr_not_ai_benchmark',
                                 'started_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'passed':False,
                                 'failures':[],'runs':[],'ai_requests_expected':0}
    fixtures=RUNTIME/'ocr-continuation-fixtures';started=time.monotonic()
    try:
        with httpx.Client(base_url=args.base,timeout=90,trust_env=False) as client:
            request(client,'POST','/api/session')
            save(RUNTIME/'source-ocr-qa-session.json',dict(client.cookies),True)
            wallet=request(client,'GET','/api/wallet')
            with sqlite3.connect(RUNTIME/'study.sqlite3') as db:
                before_usage=db.execute('select count(*) from ai_usage').fetchone()[0]
            raw=(fixtures/'networking-47-pages.pdf').read_bytes();upload=time.monotonic()
            source=request(client,'POST','/api/sources/upload',files={'file':('networking-47-pages.pdf',raw)})
            path='/api/sources/'+source['id'];original=copy.deepcopy(source)
            print('PDF uploaded; protecting a manual correction',flush=True)
            texts=[f['text'] for f in source['fragments']]
            index=next(i for i,f in enumerate(source['fragments']) if f['locator'].get('page')==24 and f['text'].startswith('QA native page'))
            texts[index]='QA manual correction page 24 — retain this exact text'
            source=request(client,'POST',path+'/save-draft',json={'expected_revision':source['revision'],'texts':texts})
            assert not source['reviewed'];manual=copy.deepcopy(source)
            status=request(client,'GET',path+'/ocr-status')
            assert status['total_items']==47 and status['counts']['protected']==1,status
            assert status['next_items']==['page:'+str(i) for i in range(21,42) if i!=24],status
            start=request(client,'POST',path+'/ocr-batches',json={'expected_revision':source['revision']},
                          headers={'Idempotency-Key':'native-continuation-cancel'})
            job_id=start['job_id'];cancelled=None;before_cancel=None
            for _ in range(400):
                job=request(client,'GET','/api/jobs/'+job_id)
                batch_id=job['context']['ocr_batch_id']
                preview=request(client,'GET','/api/ocr-batches/'+batch_id)
                if 2<=preview['completed_count']<20 and job['status']=='running':
                    before_cancel=copy.deepcopy(preview);cancelled=request(client,'POST','/api/jobs/'+job_id+'/cancel',json={});break
                if job['status'] not in {'queued','running'}:break
                time.sleep(.02)
            assert cancelled is not None,'Native pass completed before cancellation checkpoint was observed'
            for _ in range(50):
                preview=request(client,'GET','/api/ocr-batches/'+batch_id)
                resumed=client.post('/api/ocr-batches/'+batch_id+'/resume',json=action(preview),headers={'Idempotency-Key':'native-continuation-resume'})
                if resumed.status_code!=409:break
                time.sleep(.05)
            resumed.raise_for_status();job2=wait_job(client,resumed.json()['job_id'])
            assert job2['status']=='succeeded',job2
            batch=request(client,'GET','/api/ocr-batches/'+batch_id)
            complete_keys=[key for key,value in before_cancel['results'].items() if value['state'] in {'text','no_text'}]
            assert all(batch['results'][key]==before_cancel['results'][key] for key in complete_keys)
            assert request(client,'GET',path)['revision']==manual['revision']
            assert batch['completed_count']==20 and not batch['remaining_count'],batch
            source=request(client,'POST','/api/ocr-batches/'+batch_id+'/apply',json=action(batch))
            assert not source['reviewed']
            status=request(client,'GET',path+'/ocr-status');assert status['next_items']==['page:'+str(i) for i in range(42,48)]
            second,second_job=finish(client,source)
            source=request(client,'POST','/api/ocr-batches/'+second['id']+'/apply',json=action(second))
            final=request(client,'GET',path+'/ocr-status')
            assert final['counts']['pending']==0 and final['counts']['protected']==1,final
            assert final['counts']['text_available_unverified']==46,final
            assert request(client,'GET',path+'?revision='+str(manual['revision']))['fragments']==manual['fragments']
            assert any(f['text']==texts[index] for f in source['fragments'])
            assert hashlib.sha256(client.get(path+'/original').content).hexdigest()==hashlib.sha256(raw).hexdigest()
            data['runs'].append({'kind':'pdf','source_id':source['id'],'pdf_flow_seconds_through_two_passes':round(time.monotonic()-upload,3),
                                 'initial_fragments':len(original['fragments']),'counts_after_first_apply':status['counts'],
                                 'manual_page':24,'cancelled_job':job_id,'checkpoint_items_reused':complete_keys,
                                 'batch_ids':[batch_id,second['id']],'resume_job':job2['id'],
                                 'final_revision':source['revision'],'final_counts':final['counts'],
                                 'original_sha256':hashlib.sha256(raw).hexdigest(),'old_revision_and_manual_text_unchanged':True,
                                 'reviewed':source['reviewed']})
            print('PDF: cancelled/resumed without rereading completed pages; 46 OCR + 1 protected',flush=True)

            for name,keys,kind in [('networking-47-frames.tiff',['frame:21','frame:47'],'image'),
                                   ('networking-23-slides.pptx',None,'office')]:
                raw=(fixtures/name).read_bytes();begin=time.monotonic()
                item=request(client,'POST','/api/sources/upload',files={'file':(name,raw)})
                current=request(client,'GET','/api/sources/'+item['id']+'/ocr-status')
                if kind=='office':assert current['counts']['pending']==3,current
                read,job=finish(client,item,keys)
                if kind=='image':
                    assert read['results']['frame:21']['state']=='text'
                    assert read['results']['frame:47']['state']=='no_text'
                item=request(client,'POST','/api/ocr-batches/'+read['id']+'/apply',json=action(read))
                current=request(client,'GET','/api/sources/'+item['id']+'/ocr-status')
                if kind=='image':
                    assert current['counts']['no_text_detected']==1 and 'frame:47' not in current['next_items']
                else:assert current['counts']['pending']==0 and current['counts']['text_available_unverified']==23,current
                data['runs'].append({'kind':kind,'source_id':item['id'],'batch_id':read['id'],'job_id':job['id'],
                                     'elapsed_seconds':round(time.monotonic()-begin,3),'completed_items':read['completed_count'],
                                     'no_text_detected':read['no_text_count'],'final_counts':current['counts'],'reviewed':item['reviewed']})
                print(kind+': real native pass applied as unreviewed extraction',flush=True)
            assert request(client,'GET','/api/wallet')==wallet
            with sqlite3.connect(RUNTIME/'study.sqlite3') as db:
                after_usage=db.execute('select count(*) from ai_usage').fetchone()[0]
            assert before_usage==after_usage
            data.update(passed=True,coin_wallet_unchanged=True,ai_usage_rows_added=after_usage-before_usage,
                        native_provider='macOS_Vision',notes=['OCR recognition quality is not fully verified.',
                        'Frame47 is a known synthetic white frame; the product only reports no text detected.',
                        'The cancelled in-flight page can be retried; already completed pages are retained.'])
    except Exception as exc:
        data['failures'].append({'type':type(exc).__name__,'message':str(exc)[:1500]});raise
    finally:
        data['elapsed_seconds']=round(time.monotonic()-started,3);save(EVIDENCE,data)
        print(json.dumps({'passed':data['passed'],'runs':len(data['runs']),'evidence':str(EVIDENCE.relative_to(ROOT))}),flush=True)


if __name__=='__main__':main()
