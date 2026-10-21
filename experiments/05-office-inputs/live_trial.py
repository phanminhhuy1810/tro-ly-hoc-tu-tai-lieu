"""Bounded localhost trial on self-authored inputs. Max 3 AI jobs, no retries."""
from pathlib import Path
import hashlib
import json
import sys
import time
import uuid
import httpx

ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
REPORT=ROOT/'backend/evidence/office-capacity-live-trial.json'
report={'purpose':'Functional localhost trial on self-authored development fixtures, not a held-out AI-quality benchmark','calls':[],'failures':[]}
session_file=ROOT/'backend/runtime/office-capacity-qa-session.json'
client=httpx.Client(base_url='http://127.0.0.1:8770',timeout=60,cookies=json.loads(session_file.read_text()) if session_file.exists() else None)
coin_total=0

def save():REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
def req(method,path,**kwargs):
    response=client.request(method,'/api'+path,**kwargs);response.raise_for_status();return response.json()
def ai(path,body):
    global coin_total
    assert len(report['calls'])<3
    headers={'Idempotency-Key':uuid.uuid4().hex};start=time.monotonic()
    response=client.post('/api'+path,json=body,headers=headers)
    if response.status_code==402:
        quote=response.json()['detail'];assert coin_total+quote['amount']<=8
        coin_total+=quote['amount'];headers['Coin-Quote-Id']=quote['quote_id']
        response=client.post('/api'+path,json=body,headers=headers)
    response.raise_for_status();job_id=response.json()['job_id']
    print('started',path,job_id,flush=True)
    deadline=time.monotonic()+185
    while time.monotonic()<deadline:
        job=req('GET','/jobs/'+job_id)
        if job['status'] in {'succeeded','failed','cancelled'}:break
        time.sleep(.5)
    else:
        req('POST','/jobs/'+job_id+'/cancel',json={});job=req('GET','/jobs/'+job_id)
    item={'path':path,'job_id':job_id,'elapsed_seconds':round(time.monotonic()-start,3),'status':job['status'],'error':job['error'],'provider':job['provider'],'result':job['result']}
    report['calls'].append(item);report['proposed_coin_confirmed']=coin_total;save()
    print('finished',path,job['status'],item['elapsed_seconds'],flush=True)
    return job

def main():
    req('POST','/session',json={})
    cookies=ROOT/'backend/runtime/office-capacity-qa-session.json';cookies.write_text(json.dumps(dict(client.cookies)));cookies.chmod(0o600)
    catalog=req('GET','/ai/models');gemini=next(m for m in catalog['models'] if m['provider']=='gemini_api' and m['selectable'])
    req('PUT','/ai/selection',json={'model_id':gemini['id'],'expected_revision':catalog['selection_revision'],'allow_external':True})
    report['limits']=req('GET','/source-limits')
    path=HERE/'fixtures/office-dev.docx';raw=path.read_bytes()
    with path.open('rb') as file:source=req('POST','/sources/upload',files={'file':(path.name,file,'application/vnd.openxmlformats-officedocument.wordprocessingml.document')})
    source_path='/sources/'+source['id'];assets=req('GET',source_path+'/assets')['assets'];asset=assets[0]
    before=source['fragments'];old_hash=hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest()
    job=ai(source_path+'/vision-review',{'expected_revision':source['revision'],'asset_id':asset['id']})
    expected=(ROOT/'experiments/03-ocr-inputs/fixtures/networking.txt').read_text().strip()
    if job['status']=='succeeded':
        parent=req('GET','/source-proposals/'+job['result']['source_proposal_id'])
        child=req('POST','/source-proposals/'+parent['id']+'/edit-preview',json={'expected_revision':source['revision'],'text':expected})
        report['vision_parent']={k:parent[k] for k in ['id','model','text','uncertain_spans','dimensions']}
        assert req('GET','/source-proposals/'+parent['id'])['text']==parent['text']
    else:
        report['failures'].append({'stage':'office_vision','job_id':job['id'],'error':job['error']})
        child=req('POST',source_path+'/assets/'+asset['id']+'/transcription-preview',json={'expected_revision':source['revision'],'text':expected})
    updated=req('POST','/source-proposals/'+child['id']+'/apply',json={'expected_revision':source['revision']})
    unaffected=lambda fs:[{k:v for k,v in f.items() if k!='id'} for f in fs if f['locator'].get('asset_id')!=asset['id']]
    assert unaffected(before)==unaffected(updated['fragments'])
    assert hashlib.sha256(json.dumps(req('GET',source_path+'?revision=1')['fragments'],sort_keys=True).encode()).hexdigest()==old_hash
    assert client.get('/api'+source_path+'/original').content==raw
    report['office_manual_apply']={'source_id':source['id'],'asset_id':asset['id'],'proposal_id':child['id'],'before_revision':source['revision'],'after_revision':updated['revision'],'still_requires_review':not updated['reviewed'],'original_unchanged':True,'old_revision_unchanged':True,'native_text_and_other_images_unchanged':True,'manual_text':expected}
    # Whole-source planning is free; AI sees only the first lesson's exact scope.
    lines=(HERE/'fixtures/network-notes.txt').read_text().splitlines();sources=[]
    for i,part in enumerate((lines[:40],lines[40:]),1):
        sources.append(req('POST','/sources/text',json={'name':'QA network chapter '+str(i),'text':'\n'.join(part)}))
    source=req('POST','/sources/collection',json={'name':'QA multiple-source network course','sources':[{'source_id':s['id'],'expected_revision':s['revision']} for s in sources]})
    source=req('POST','/sources/'+source['id']+'/review',json={'expected_revision':source['revision'],'texts':[f['text'] for f in source['fragments']]})
    plan=req('POST','/plans/from-source-sections',json={'source_id':source['id'],'expected_extraction_revision':source['revision'],'subject':'QA networking development fixture','goal':'Learn the selected source facts in English','language':'en','fragment_ids':[f['id'] for f in source['fragments']],'question_types':['mcq'],'question_count':1,'card_count':1})
    assert [r for u in plan['outline']['units'] for r in u['source_refs']]==[f['id'] for f in source['fragments']]
    course_id=req('POST','/plans/'+plan['id']+'/approve',json={'expected_revision':1})['course_id']
    job=ai('/courses/'+course_id+'/generate',{'expected_revision':1,'unit_id':'unit-1'})
    course=req('GET','/courses/'+course_id)
    report['long_scope']={'source_id':source['id'],'plan_id':plan['id'],'course_id':course_id,'selected_fragments':80,'assigned_fragments':sum(len(u['source_refs']) for u in plan['outline']['units']),'units':len(plan['outline']['units']),'planning_method':plan['outline']['method'],'planning_ai_calls':0,'first_unit_refs':plan['outline']['units'][0]['source_refs'],'generation_job_id':job['id']}
    if job['status']=='succeeded':
        unit=course['content']['units'][0];allowed=set(unit['source_refs']);lesson=unit['data'];assert all(set(item['source_refs'])<=allowed for field in ['sections','cards','mindmap','questions'] for item in lesson[field])
        report['first_unit']={'course_revision':course['revision'],'unit_id':unit['id'],'source_refs':unit['source_refs'],'lesson':lesson,'other_units_not_generated':all(u['data'] is None for u in course['content']['units'][1:])}
    else:report['failures'].append({'stage':'first_unit_generation','job_id':job['id'],'error':job['error']})
    report['provider_default_unchanged']=req('GET','/ai/models')['default_model_id']==catalog['default_model_id']
    save();print('report_saved',REPORT.name,flush=True)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        report['failures'].append({'stage':'trial','error_type':type(exc).__name__,'message':str(exc)[:500] if not isinstance(exc,httpx.HTTPError) else 'HTTP request failed; inspect local endpoint and saved stage.'});save();print('trial_failed',type(exc).__name__,flush=True);raise
