"""Continue the existing self-authored trial. No browser/auth extraction or fake provider."""
import asyncio,copy,json,time,uuid
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[2]
record={'purpose':'real HTTP/Qwen9B revision/future-plan/short-feedback development trial; not human benchmark','checks':{},'jobs':[]}
async def main():
 previous=json.loads((ROOT/'backend/evidence/learning-live-trial.json').read_text())
 async with httpx.AsyncClient(base_url='http://127.0.0.1:8770',timeout=210,trust_env=False) as client:
  client.cookies.update(json.loads((ROOT/'backend/runtime/smoke-learning-session.json').read_text()))
  async def api(method,path,data=None):
   response=await client.request(method,'/api'+path,json=data);response.raise_for_status();return response.json()
  async def job(path,data):
   response=await client.post('/api'+path,json=data,headers={'Idempotency-Key':uuid.uuid4().hex});response.raise_for_status();started=response.json()
   if 'job_id' not in started:return started
   stamp=time.monotonic()
   while time.monotonic()-stamp<210:
    value=await api('GET','/jobs/'+started['job_id'])
    if value['status'] in ['succeeded','failed','cancelled']:
     record['jobs'].append({'id':value['id'],'status':value['status'],'provider':value['provider'],'error':value['error'],'elapsed_seconds':round(time.monotonic()-stamp,3)})
     assert value['status']=='succeeded',value['error'];return value['result']
    await asyncio.sleep(1)
   raise RuntimeError('timeout; server job retained')
  course=await api('GET','/courses/'+previous['course_id']+'/editor');path='/courses/'+course['id'];record['course_id']=course['id'];record['base_revision']=course['revision']
  preview=await api('POST',path+'/revert-preview',{'expected_revision':course['revision'],'target_revision':2,'unit_id':'unit-1'})
  candidate=await api('GET','/proposals/'+preview['proposal_id'])
  assert candidate['scope']['target']=='revert'
  assert (await api('GET',path))['revision']==course['revision']
  await api('POST','/proposals/'+preview['proposal_id']+'/discard')
  record['checks']['revert_preview_does_not_apply_and_can_discard']=True
  old=await api('GET','/sessions/'+previous['session_id']);short=next(q for q in old['questions'] if q['kind']=='short_answer')
  await job('/sessions/'+old['id']+'/short-feedback',{'item_id':short['id']})
  feedback=await api('GET','/sessions/'+old['id']+'/short-feedback')
  assert feedback and feedback[-1]['verified_score'] is False and feedback[-1]['estimated_score'] is None
  assert (await api('GET','/sessions/'+old['id']))['result']==old['result']
  record['feedback']=feedback[-1];record['checks']['rubric_feedback_does_not_change_old_fixed_score']=True
  unit=course['content']['units'][1]
  body={'expected_revision':course['revision'],'units':[{'unit_id':unit['id'],'title':'Host bits and block size','objective':'Understand from the source that 6 host bits create 64 addresses.','source_refs':unit['source_refs']}],
        'preferences':{'language':'en','goal':'Review the remaining units using source facts','question_types':['mcq','cloze'],'question_count':2,'card_count':1,'unlock_policy':'open'},'request':'Dev trial: adjust only the ungenerated next unit; preserve generated material.'}
  proposal=await api('POST',path+'/future-plan-preview',body)
  candidate=await api('GET','/proposals/'+proposal['proposal_id'])
  assert candidate['after']['units'][0]['data']==course['content']['units'][0]['data']
  applied=await api('POST','/proposals/'+proposal['proposal_id']+'/apply',{'expected_revision':course['revision']})
  await job(path+'/generate',{'expected_revision':applied['revision'],'unit_id':unit['id']})
  updated=await api('GET',path+'/editor')
  assert updated['content']['units'][0]['data']==course['content']['units'][0]['data']
  generated=updated['content']['units'][1]
  assert len(generated['data']['questions'])==2 and len(generated['data']['cards'])==1
  record['new_revision']=updated['revision'];record['new_unit']=generated
  record['checks']['future_edit_preserves_generated_lesson']=True
  record['checks']['two_selected_types_and_one_card']=True
  record['checks']['old_attempt_revision_unchanged']=(await api('GET','/sessions/'+old['id']))['revision']==old['revision']
  record['passed']=True
try:asyncio.run(main())
except Exception as exc:record['passed']=False;record['error']=str(exc);print('TRIAL FAILED',type(exc).__name__,str(exc),flush=True)
finally:
 file=ROOT/'backend/evidence/revision-feedback-live-trial.json';file.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n');print('saved',file,'passed',record.get('passed'),flush=True)
