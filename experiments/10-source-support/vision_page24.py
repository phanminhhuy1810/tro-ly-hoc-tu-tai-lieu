"""One local visual reread of the actual page24 raster; retain raw failures."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import time

import httpx

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
path=HERE/'results/page24-vision.json'
if path.exists():raise SystemExit('This image trial already exists; inspect saved IDs, do not regenerate.')
path.parent.mkdir(parents=True,exist_ok=True)
image=ROOT/'backend/runtime/chapter-visual-audit/page-24.png'
native=json.loads((image.parent/'page-24-native.json').read_text())
report={'purpose':'Single local source-vision trial of the actual PDF page24 raster after native OCR missed zero cells. Not a general OCR accuracy score.',
        'started_at':datetime.now(timezone.utc).isoformat(),'raster_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),
        'native_text':native['text'],'native_engine':native.get('engine'),'model':'local:gemma4:12b-mlx',
        'max_inference_calls':1,'max_seconds':210,'external_inference':0,'payments':0,'applied':False,'human_reviewed':False}
def save():path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
with httpx.Client(base_url='http://127.0.0.1:8770',timeout=30,trust_env=False) as client:
    def call(method,route,body=None):
        response=client.request(method,'/api'+route,json=body);response.raise_for_status();return response.json()
    profile=call('POST','/session');report['qa_owner_id']=profile['id']
    private=ROOT/'backend/runtime/chapter-visual-audit/qa-session.json';private.touch(mode=0o600);private.write_text(json.dumps(dict(client.cookies))+'\n');private.chmod(0o600)
    catalog=call('GET','/ai/models');call('PUT','/ai/selection',{'model_id':report['model'],'expected_revision':catalog['selection_revision'],'allow_external':False})
    with image.open('rb') as f:response=client.post('/api/sources/upload',files={'file':('QA PDF page24.png',f,'image/png')})
    response.raise_for_status();source=response.json();report['source_before']=source
    report['wallet_before']=call('GET','/wallet');save()
    route='/api/sources/'+source['id']+'/vision-review';body={'expected_revision':source['revision'],'page':1};headers={'Idempotency-Key':'page24-visual-review-local'}
    response=client.post(route,json=body,headers=headers)
    if response.status_code==402:
        quote=response.json()['detail'];report['quote_amount']=quote['amount'];save()
        if quote['amount']>2:raise RuntimeError('Unexpected QA price; no confirmation.')
        headers['Coin-Quote-Id']=quote['quote_id'];response=client.post(route,json=body,headers=headers)
    response.raise_for_status();jid=response.json()['job_id'];report['job_id']=jid;save()
    began=time.monotonic()
    while True:
        job=call('GET','/jobs/'+jid)
        if job['status'] in {'succeeded','failed','cancelled'}:break
        if time.monotonic()-began>205:call('POST','/jobs/'+jid+'/cancel',{});break
        time.sleep(.8)
    report['job']=call('GET','/jobs/'+jid);report['elapsed_seconds']=round(time.monotonic()-began,3)
    if report['job']['status']=='succeeded':
        report['proposal']=call('GET','/source-proposals/'+report['job']['result']['source_proposal_id'])
    report['source_revision_after']=call('GET','/sources/'+source['id'])['revision'];report['wallet_after']=call('GET','/wallet')
    report['status']=report['job']['status'];save()
print(json.dumps({'status':report['status'],'elapsed_seconds':report['elapsed_seconds'],'proposal_id':report.get('proposal',{}).get('id')},ensure_ascii=False),flush=True)
