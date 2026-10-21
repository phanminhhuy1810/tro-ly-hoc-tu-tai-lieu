"""Bounded, explicitly scoped corrections on the self-authored trial only."""
import asyncio,json,time,uuid
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[2]
async def main():
 file=ROOT/'backend/evidence/revision-feedback-live-trial.json';report=json.loads(file.read_text())
 async with httpx.AsyncClient(base_url='http://127.0.0.1:8770',timeout=210,trust_env=False) as c:
  c.cookies.update(json.loads((ROOT/'backend/runtime/smoke-learning-session.json').read_text()))
  async def api(method,path,body=None):
   response=await c.request(method,'/api'+path,json=body);response.raise_for_status();return response.json()
  base='/courses/'+report['course_id']; original=await api('GET',base+'/editor');initial_cards=original['content']['units'][1]['data']['cards'];first_lesson=original['content']['units'][0]['data']
  attempts=[]
  for index in [0,1]:
   course=await api('GET',base+'/editor')
   started=await api('POST',base+'/proposals',{'expected_revision':course['revision'],'unit_id':course['content']['units'][1]['id'],'target':'question','index':index,'request':'Rewrite this question prompt, options, explanation and rubric in English. Preserve the original source facts and correct numeric answer. Do not create extra content.'})
   stamp=time.monotonic()
   while time.monotonic()-stamp<210:
    job=await api('GET','/jobs/'+started['job_id'])
    if job['status'] in ['failed','cancelled','succeeded']:break
    await asyncio.sleep(1)
   attempts.append({'id':job['id'],'status':job['status'],'error':job['error'],'provider':job['provider']})
   if job['status']!='succeeded':
    report['language_review'].update(status='targeted_ai_correction_failed',correction_jobs=attempts);file.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print('CORRECTION FAILED',job['error']);return
   proposal=await api('GET','/proposals/'+job['result']['proposal_id'])
   assert (await api('GET',base))['revision']==course['revision']
   await api('POST','/proposals/'+proposal['id']+'/apply',{'expected_revision':course['revision']})
  final=await api('GET',base+'/editor')
  assert final['content']['units'][0]['data']==first_lesson
  assert final['content']['units'][1]['data']['cards']==initial_cards
  report['language_review'].update(status='scoped_corrections_applied_needs_content_review',correction_jobs=attempts,corrected_revision=final['revision'],corrected_questions=final['content']['units'][1]['data']['questions'],reading_and_cards_preserved=True,first_lesson_preserved=True)
  file.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
  print(json.dumps(report['language_review']['corrected_questions'],ensure_ascii=False))
asyncio.run(main())
