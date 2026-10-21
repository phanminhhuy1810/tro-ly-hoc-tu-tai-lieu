"""Real localhost HTTP/OCR/model trial with self-authored input. No human benchmark."""
import asyncio, hashlib, json, time, uuid, sys
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parents[2]
resume='--resume' in sys.argv
report={'purpose':'script-controlled real HTTP/native OCR/Qwen9B development trial; not independent learner or final benchmark','checks':{},'jobs':[]}

if resume:
 old=json.loads((ROOT/'backend/evidence/learning-live-trial.json').read_text()); report.update(old); report.setdefault('previous_failures',[]).append({'error':old.get('error'),'jobs':old.get('jobs',[])}); report['jobs']=[]; report.pop('error',None)

async def main():
 async with httpx.AsyncClient(base_url='http://127.0.0.1:8770',timeout=210,trust_env=False) as client:
  async def api(method,path,body=None,**kwargs):
   response=await client.request(method,'/api'+path,json=body,**kwargs)
   response.raise_for_status(); return response.json()
  async def job(path,body):
   intent={'Idempotency-Key':uuid.uuid4().hex}; started=await api('POST',path,body,headers=intent); stamp=time.monotonic()
   repeated=await api('POST',path,body,headers=intent); assert repeated==started
   while time.monotonic()-stamp<210:
    value=await api('GET','/jobs/'+started['job_id'])
    if value['status'] in ['succeeded','failed','cancelled']:
     report['jobs'].append({'id':value['id'],'status':value['status'],'elapsed_seconds':round(time.monotonic()-stamp,3),'error':value['error'],'partial_saved':bool(value['partial'])})
     assert value['status']=='succeeded', value['error']
     return value['result']
    await asyncio.sleep(1)
   raise RuntimeError('job timeout; kept server job and partial')
  cookiefile=ROOT/'backend/runtime/smoke-learning-session.json'
  if resume:
   client.cookies.update(json.loads(cookiefile.read_text()))
   source=await api('GET','/sources/'+report['source_id'])
   assert source['reviewed']
  else:
   await api('POST','/session')
   cookiefile.write_text(json.dumps(dict(client.cookies))); cookiefile.chmod(0o600)
   data=(ROOT/'experiments/03-ocr-inputs/fixtures/networking.png').read_bytes()
   response=await client.post('/api/sources/upload',files={'file':('networking.png',data,'image/png')}); response.raise_for_status(); source=response.json()
   report['source_id']=source['id']; report['checks']['ocr_requires_review']=not source['reviewed']
   original=await client.get('/api/sources/'+source['id']+'/original'); assert original.content==data
   report['checks']['original_bytes_preserved']=True
   expected=(ROOT/'experiments/03-ocr-inputs/fixtures/networking.txt').read_text().splitlines()
   assert len(source['fragments'])==len(expected)
   source=await api('POST','/sources/'+source['id']+'/review',{'expected_revision':1,'texts':expected})
   report['extraction_revision']=source['revision']; report['checks']['corrected_power_and_reviewed']=source['reviewed'] and any('2^6' in f['text'] for f in source['fragments'])
  prefs={'source_id':source['id'],'subject':'Mạng máy tính','goal':'Hiểu subnet /26 và tính network/broadcast/host từ nguồn này','instructions':'Nguồn kiểm thử tự soạn. Chỉ dùng nội dung có trong nguồn. Không tạo quy trình có thứ tự nếu nguồn không viết rõ.','fragment_ids':[f['id'] for f in source['fragments']],'language':'vi'}
  if resume and report.get('course_id'):
   course=report['course_id']
   failed=report['previous_failures'][-1]['jobs'][-1]['id']
   await job('/courses/'+course+'/generate',{'expected_revision':1,'unit_id':'unit-1','resume_job_id':failed})
  else:
   planned=await job('/plans',prefs)
   plan=await api('GET','/plans/'+planned['plan_id']); report['plan_id']=plan['id']
   # Explicitly script-approved for backend development; not a Huy review claim.
   course=(await api('POST','/plans/'+plan['id']+'/approve',{'expected_revision':plan['outline']['version']}))['course_id']; report['course_id']=course
   await job('/courses/'+course+'/generate',{'expected_revision':1,'unit_id':'unit-1'})
  editor=await api('GET','/courses/'+course+'/editor'); revision=editor['revision']; report['course_revision']=revision
  qs=editor['content']['units'][0]['data']['questions']; report['question_types']=[q['kind'] for q in qs]
  session=await api('POST','/courses/'+course+'/sessions',{'expected_revision':revision,'unit_id':'unit-1'},headers={'Idempotency-Key':'smoke-practice-once'}); report['session_id']=session['id']
  draft=await api('PUT','/sessions/'+session['id']+'/draft',{'item_id':session['questions'][0]['id'],'answer':'draft only','expected_version':0}); assert draft['graded'] is False
  for item,q in zip(session['questions'],qs):
   if q['kind']=='mcq': answer=next(o['id'] for o in item['payload']['options'] if o['text']!=q['answer'])
   elif q['kind']=='cloze': answer='intentionally wrong value'
   elif q['kind']=='short_answer': answer='Chưa hiểu; tự đối chiếu sau.'
   else:
    wrong=q['answer'][1:]+q['answer'][:1]; answer=[f'option-{i}' for i in wrong]
    if q['kind']=='matching': answer={f'left-{i}':v for i,v in enumerate(answer)}
   await api('POST','/sessions/'+session['id']+'/answers',{'item_id':item['id'],'answer':answer})
  result=await api('POST','/sessions/'+session['id']+'/complete'); report['practice_result']=result; assert result['score']==0
  nowcourse=await api('GET','/courses/'+course); report['checks']['zero_score_unlocks_next']=len(nowcourse['content']['units'])<2 or nowcourse['content']['units'][1]['unlocked']
  item=session['questions'][0]
  card=await api('POST','/cards/from-question',{'session_id':session['id'],'item_id':item['id']}); repeat=await api('POST','/cards/from-question',{'session_id':session['id'],'item_id':item['id']}); assert card['id']==repeat['id']
  await api('PUT','/cards/'+card['id']+'/memory',{'remembered':False,'expected_version':0,'course_id':course})
  saved=await api('GET','/cards?course_id='+course+'&only_unremembered=true'); assert any(c['id']==card['id'] for c in saved)
  report['checks']['save_question_once_and_unremembered']=True
  note=await api('POST','/notebook',{'body':'Nguồn tự soạn: cần đối chiếu 2^6, không dùng 216 từ OCR.','label':'user','course_id':course,'source_refs':qs[0]['source_refs']})
  report['note_id']=note['id']; assert note['label']=='user'
  report['checks']['notebook_saved_to_db']=True
  bank=await api('GET','/courses/'+course); assert all('answer' not in q for q in bank['content']['units'][0]['data']['questions']); report['checks']['reader_payload_has_no_keys']=True
  exam=await api('POST','/courses/'+course+'/sessions',{'expected_revision':revision,'unit_id':'unit-1','exercise':'test','question_types':['mcq'],'question_count':1})
  eq=exam['questions'][0]; correct=next(o['id'] for o in eq['payload']['options'] if o['text']==qs[0]['answer'])
  exam_reply=await api('POST','/sessions/'+exam['id']+'/answers',{'item_id':eq['id'],'answer':correct}); assert exam_reply['accepted'] and 'correct' not in exam_reply
  assert (await api('GET','/sessions/'+exam['id']))['answers'][eq['id']]['feedback'] is None
  assert (await api('GET','/sessions/'+session['id']))['answers'][item['id']]['feedback'] is None
  assert (await api('POST','/sessions/'+exam['id']+'/complete'))['score']==1
  report['checks']['test_feedback_hidden_until_final']=True
  async with httpx.AsyncClient(base_url='http://127.0.0.1:8770',trust_env=False) as foreign:
   await foreign.post('/api/session'); assert (await foreign.get('/api/notebook')).json()==[]
   assert (await foreign.get('/api/sources/'+source['id'])).status_code==404
  report['checks']['private_in_other_profile']=True
  report['passed']=True
try: asyncio.run(main())
except Exception as exc: report['passed']=False; report['error']=str(exc); print('TRIAL FAILED:',type(exc).__name__,str(exc),flush=True)
finally:
 target=ROOT/'backend/evidence/learning-live-trial.json'; target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n'); print('saved',target,'passed',report.get('passed'),flush=True)
