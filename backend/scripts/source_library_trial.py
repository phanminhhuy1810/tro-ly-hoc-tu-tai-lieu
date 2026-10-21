"""Bounded local HTTP check of source pages/selection. No model call or Coin quote."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from datetime import datetime, timezone
import httpx

ROOT=Path(__file__).resolve().parents[2]
RUNTIME=ROOT/'backend/runtime'

def counters():
    with sqlite3.connect(f'file:{RUNTIME / "study.sqlite3"}?mode=ro',uri=True) as db:
        return {table:db.execute('select count(*) from '+table).fetchone()[0] for table in ('jobs','ai_usage','coin_ledger')}

async def run():
    report={'purpose':'Local source-library HTTP functional test with self-authored fixtures; not a model-quality or multi-user load benchmark', 'started_at':datetime.now(timezone.utc).isoformat(),'checks':{}}
    before=counters()
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8770',timeout=20,trust_env=False) as client:
        async def api(method,path,body=None,params=None):
            response=await client.request(method,'/api'+path,json=body,params=params);response.raise_for_status();return response.json()
        owner=await api('POST','/session',{})
        private=RUNTIME/'source-library-qa-session.json';private.write_text(json.dumps(dict(client.cookies))+'\n');os.chmod(private,0o600)
        sources=[]
        for i in range(115):sources.append(await api('POST','/sources/text',{'name':f'Source-library QA {i:03d} · Địa chỉ_100%' if i==37 else f'Source-library QA {i:03d}', 'text':f'Self-authored navigation fixture {i}: IPv4 uses 32 bits.'}))
        first=await api('GET','/source-library')
        fresh=await api('POST','/sources/text',{'name':'Source-library QA newest after page1','text':'New source must appear only in a fresh source-list window.'})
        ids=[x['id'] for x in first['items']];page=first;pages=1
        while page['next_cursor']:
            if pages>10:raise RuntimeError('bounded page walk exceeded')
            page=await api('GET','/source-library',params={'cursor':page['next_cursor']});ids.extend(x['id'] for x in page['items']);pages+=1
        checks=report['checks'];checks['past100_exact_once']=ids==[x['id'] for x in reversed(sources)] and len(set(ids))==115
        checks['new_upload_not_in_old_window']=fresh['id'] not in ids
        back=await api('GET','/source-library',params={'cursor':first['current_cursor']})
        checks['back_keeps_window']=back['items']==first['items']
        checks['fresh_page_sees_upload']=(await api('GET','/source-library'))['items'][0]['id']==fresh['id']
        accent=await api('GET','/source-library',params={'q':'DIA CHI % _'})
        checks['literal_accent_search']=[x['id'] for x in accent['items']]==[sources[37]['id']]
        async with httpx.AsyncClient(base_url='http://127.0.0.1:8770',timeout=20,trust_env=False) as other:
            (await other.post('/api/session',json={})).raise_for_status()
            hidden=await other.get('/api/sources/'+sources[0]['id']+'/fragments',params={'revision':1})
            wrongcursor=await other.get('/api/source-library',params={'cursor':first['current_cursor']})
            checks['foreign_source_denied']=hidden.status_code==404 and 'Self-authored' not in hidden.text
            checks['foreign_cursor_denied']=wrongcursor.status_code==422
        text='\n'.join(f'Địa chỉ IPv4 mục {i}: IPv4 has 32 bits.' if i%10==0 else f'Concept {i}: read the source before creating a lesson.' for i in range(180))
        source=await api('POST','/sources/text',{'name':'Source-library QA 180 excerpts','text':text});sid=source['id'];base='/sources/'+sid
        original=(await client.get('/api'+base+'/original')).content;original_hash=hashlib.sha256(original).hexdigest()
        source=await api('POST',base+'/review',{'expected_revision':source['revision'],'texts':[f['text'] for f in source['fragments']]})
        query={'revision':2,'q':'dia chi','limit':5}
        p1=await api('GET',base+'/fragments',params=query);p2=await api('GET',base+'/fragments',params={**query,'offset':5})
        selection=await api('GET',base+'/fragment-selection',params={'revision':2,'q':'dia chi'})
        expected=[f['id'] for i,f in enumerate(source['fragments']) if i%10==0]
        checks['search_across_fragment_pages']=p1['matched_fragments']==18 and not ({x['id'] for x in p1['items']}&{x['id'] for x in p2['items']})
        checks['all_matching_ids_exact']=selection['fragment_ids']==expected
        preferences={'source_id':sid,'expected_extraction_revision':2,'subject':'Mạng máy tính','goal':'Only the selected eighteen excerpts','language':'vi','fragment_ids':expected}
        plan=await api('POST','/plans/from-source-sections',preferences)
        assigned=[r for u in plan['outline']['units'] for r in u['source_refs']]
        checks['preview_exact_scope']=assigned==expected and plan['status']=='preview'
        source=await api('POST',base+'/review',{'expected_revision':2,'texts':[f['text']+' Reviewed again.' for f in source['fragments']]})
        old=await api('GET',base+'/fragments',params=query)
        checks['old_revision_immutable']=old['items']==p1['items'] and old['latest_revision']==3
        stale=await client.post('/api/plans/from-source-sections',json=preferences)
        checks['stale_plan_denied']=stale.status_code==409
        checks['original_unchanged']=hashlib.sha256((await client.get('/api'+base+'/original')).content).hexdigest()==original_hash
        report.update({'qa_owner_id':owner['id'],'sources_created':117,'source_pages':pages,'source_window_count':len(ids),'scope_source_id':sid,'scope_fragments':180,'matches':18,'plan_id':plan['id'],'plan_status':plan['status'],'selected_ids':expected,'source_original_sha256':original_hash})
    after=counters();report['counters_before']=before;report['counters_after']=after
    checks['no_job_ai_or_coin_write']=before==after
    report['all_passed']=all(checks.values())
    (ROOT/'backend/evidence/source-library-http-trial.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'all_passed':report['all_passed'],'checks':checks,'sources':117,'pages':pages,'matches':18},ensure_ascii=False))
    if not report['all_passed']:raise SystemExit(1)

if __name__=='__main__':asyncio.run(run())
