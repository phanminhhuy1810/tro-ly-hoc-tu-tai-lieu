"""Four script-controlled local HTTP profiles, not four independent people."""
import asyncio,json
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[2]
report={'purpose':'real HTTP four local profiles on self-authored development course; not independent human trial','checks':{},'coin_for_publishing':None}
async def main():
 prior=json.loads((ROOT/'backend/evidence/learning-live-trial.json').read_text())
 async with httpx.AsyncClient(base_url='http://127.0.0.1:8770',trust_env=False) as creator:
  creator.cookies.update(json.loads((ROOT/'backend/runtime/smoke-learning-session.json').read_text()))
  async def api(client,method,path,body=None):
   r=await client.request(method,'/api'+path,json=body);r.raise_for_status();return r.json()
  base='/courses/'+prior['course_id'];course=await api(creator,'GET',base+'/editor');report['course_id']=course['id'];report['course_revision']=course['revision']
  publication=await api(creator,'POST',base+'/publication-preview',{'expected_revision':course['revision'],'visibility':'public','share_original':False})
  assert 'notebook' in publication['preview']['private_material_excluded']
  changed=await api(creator,'POST','/publications/'+publication['publication_id']+'/apply',{'expected_revision':course['revision']});report['coin_for_publishing']=changed['coin_for_publishing'];assert report['coin_for_publishing']==0
  peers=[httpx.AsyncClient(base_url='http://127.0.0.1:8770',trust_env=False) for _ in range(3)]
  try:
   for peer in peers:
    await api(peer,'POST','/session')
    await api(peer,'POST',base+'/enroll')
    value=await api(peer,'GET',base)
    assert value['access_role']=='learner' and value['plan_id'] is None and 'preferences' not in value['content']
    assert value['content']['units'][0]['completed'] is False
    assert (await peer.get('/api/sources/'+prior['source_id']+'/original')).status_code==404
   report['checks']['creator_private_preferences_and_original_not_granted']=True
   session=await api(peers[0],'POST',base+'/sessions',{'expected_revision':course['revision'],'unit_id':'unit-1','question_types':['mcq'],'question_count':1})
   q=session['questions'][0]
   await api(peers[0],'POST','/sessions/'+session['id']+'/answers',{'item_id':q['id'],'answer':'option-0'})
   await api(peers[0],'POST','/sessions/'+session['id']+'/complete')
   assert (await peers[1].get('/api/sessions/'+session['id'])).status_code==404
   assert (await api(peers[1],'GET',base+'/history'))==[]
   report['checks']['history_and_completion_separate_between_profiles']=True
   await api(peers[0],'POST','/notebook',{'body':'private note in script-controlled learner profile','source_refs':q['source_refs'],'course_id':course['id']})
   assert (await api(peers[1],'GET','/notebook'))==[]
   report['checks']['notebook_private_on_shared_course']=True
   first=await api(peers[0],'PUT','/community/'+course['id']+'/feedback',{'liked':True,'rating':5});assert first['new_quality_event_id']
   await api(peers[0],'PUT','/community/'+course['id']+'/feedback',{'liked':False})
   assert (await api(peers[0],'PUT','/community/'+course['id']+'/feedback',{'liked':True}))['new_quality_event_id'] is None
   report['checks']['peer_quality_event_once_after_unlike_relike']=True
   publication=await api(creator,'POST',base+'/publication-preview',{'expected_revision':course['revision'],'visibility':'private','share_original':False})
   await api(creator,'POST','/publications/'+publication['publication_id']+'/apply',{'expected_revision':course['revision']})
   assert (await peers[0].get('/api/courses/'+course['id'])).status_code==404
   assert (await api(peers[0],'GET','/notebook'))[0]['body'].startswith('private note')
   report['checks']['revoke_access_keeps_personal_history_and_notes']=True
   report['passed']=True
  finally:
   for peer in peers:await peer.aclose()
try:asyncio.run(main())
except Exception as exc:report['passed']=False;report['error']=str(exc);print('TRIAL FAILED',type(exc).__name__,str(exc))
finally:
 file=ROOT/'backend/evidence/sharing-live-trial.json';file.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print('saved',file,'passed',report.get('passed'))
