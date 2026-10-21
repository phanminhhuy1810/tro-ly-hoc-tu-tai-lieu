"""Two bounded Gemini page proposals from Huy's real development PDF.

Never applies a proposal, retries generation, shares a source, or changes the
server default. --confirm-coin allows at most four proposed noncash app Coin across two page requests.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import uuid

import httpx

ROOT=Path(__file__).resolve().parents[2]
REPORT=ROOT/'backend/evidence/pdf-recovery-live-trial.json'
SOURCE=Path('/Users/phanminhhuy/Documents/learning resources/Hk4/tai lieu MMT/slide vn/CTT105-2-IP&subnetting_2.0.pdf')
result={'started_at':datetime.now(timezone.utc).isoformat(),'scope':'Developer trial on previously inspected networking PDF; not held-out, three-subject evaluation or independent human review','requests':[],'confirmed_coin':0}


def save():REPORT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')


async def api(client,method,path,body=None):
    response=await client.request(method,'/api'+path,json=body)
    response.raise_for_status();return response.json()


async def main(resume=False):
    if REPORT.exists():
        if not resume:raise RuntimeError('A trial already exists. Inspect its jobs/proposals; use --resume only to continue pages never accepted.')
        saved=json.loads(REPORT.read_text());result.clear();result.update(saved)
    elif resume:raise RuntimeError('No existing trial to resume.')
    data=SOURCE.read_bytes();result['source_sha256']=hashlib.sha256(data).hexdigest()
    if result['source_sha256']!='9037fecd5131c299809b7aa4776b782c2939b2c47c792d7ee09a5cfa6c795404':raise RuntimeError('Source changed; inspect before measuring.')
    native=json.loads((ROOT/'backend/runtime/pdf-recovery-native-after.json').read_text())
    failed=json.loads((ROOT/'backend/runtime/pdf-recovery-native.json').read_text())
    result['before_fix_timeout']={'seconds':failed['seconds'],'ocr_pages':[f['locator']['page'] for f in failed['fragments'] if f.get('provenance')],'warnings':failed['warnings']}
    result['native_after']={'seconds':native['seconds'],'ocr_pages':[f['locator']['page'] for f in native['fragments'] if f.get('provenance')],'page24':[f for f in native['fragments'] if f['locator']['page']==24],'warnings':native['warnings']}
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8770',timeout=100,trust_env=False) as client:
        private=ROOT/'backend/runtime/pdf-recovery-qa-session.json'
        if resume:client.cookies.update(json.loads(private.read_text()))
        else:
            await api(client,'POST','/session')
            private.write_text(json.dumps(dict(client.cookies)));private.chmod(0o600)
        catalogue=await api(client,'GET','/ai/models')
        await api(client,'PUT','/ai/selection',{'model_id':'gemini:gemini-2.5-flash','expected_revision':catalogue['selection_revision'],'allow_external':True})
        if resume:
            path='/sources/'+result['source_id'];source=await api(client,'GET',path)
            result.setdefault('explicit_resumes',[]).append({'at':datetime.now(timezone.utc).isoformat(),'base_revision':source['revision'],'reason':'Continue only the unaccepted second-page request after the initial two-Coin budget gate; no model retry.'});save()
        else:
            print('Uploading real PDF once; native extraction is bounded.',flush=True)
            started=time.monotonic()
            response=await client.post('/api/sources/upload',files={'file':(SOURCE.name,data,'application/pdf')});response.raise_for_status();source=response.json()
            result.update(source_id=source['id'],upload_seconds=round(time.monotonic()-started,3),extraction_revision=source['revision'],reviewed=source['reviewed'])
            path='/sources/'+source['id'];save()
            print(json.dumps({'source_id':source['id'],'upload_seconds':result['upload_seconds'],'fragments':len(source['fragments'])}),flush=True)
        original=await client.get('/api'+path+'/original');original.raise_for_status();assert original.content==data
        for page in [24,32]:
            existing=next((r for r in result['requests'] if r['page']==page),None)
            if existing:
                if existing.get('status')=='succeeded':continue
                raise RuntimeError('Retained job needs inspection; no automatic model retry: '+existing['job_id'])
            image=await client.get('/api'+path+'/page-image',params={'page':page});image.raise_for_status()
            body={'expected_revision':source['revision'],'page':page};headers={'Idempotency-Key':uuid.uuid4().hex}
            response=await client.post('/api'+path+'/vision-review',json=body,headers=headers)
            if response.status_code==402:
                quote=response.json()['detail']
                if result['confirmed_coin']+quote['amount']>4:raise RuntimeError('Explicit four-Coin QA cap reached; next page has not been submitted to AI.')
                headers['Coin-Quote-Id']=quote['quote_id']
                response=await client.post('/api'+path+'/vision-review',json=body,headers=headers)
                if response.is_success:result['confirmed_coin']+=quote['amount']
            response.raise_for_status();job_id=response.json()['job_id'];run={'page':page,'job_id':job_id};result['requests'].append(run);save()
            started=time.monotonic()
            while time.monotonic()-started<210:
                job=await api(client,'GET','/jobs/'+job_id)
                if job['status'] in {'succeeded','failed','cancelled'}:break
                await asyncio.sleep(.8)
            else:run['status']='observation_timeout_job_retained';save();raise RuntimeError('Inspect the retained job; no automatic retry.')
            run.update(status=job['status'],seconds=round(time.monotonic()-started,3),provider=job['provider'],error=job['error'])
            if job['status']=='succeeded':
                run['proposal']=await api(client,'GET','/source-proposals/'+job['result']['source_proposal_id'])
                assert run['proposal']['status']=='preview' and run['proposal']['page']==page
            save();print(json.dumps({'page':page,'status':run['status'],'seconds':run['seconds']}),flush=True)
        unchanged=await api(client,'GET',path)
        result['source_unchanged_during_resume' if resume else 'source_unchanged_until_review']=unchanged['fragments']==source['fragments'] and unchanged['revision']==source['revision']
        result['generation_finished']=all(r['status']=='succeeded' for r in result['requests'])
        result['all_proposals_left_unapplied']=not bool(result.get('page24_review',{}).get('applied_revision'))
        save()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--confirm-coin',action='store_true');parser.add_argument('--resume',action='store_true');args=parser.parse_args()
    if not args.confirm_coin:parser.error('Use --confirm-coin for at most four proposed app Coin; no payment is involved.')
    try:asyncio.run(main(args.resume))
    except Exception as exc:
        if result.get('source_id'):result['trial_error']=type(exc).__name__+': '+str(exc);save()
        raise
