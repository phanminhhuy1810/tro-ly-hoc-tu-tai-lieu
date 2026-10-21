"""One scoped, previewed correction of our Qwen QA question; zero AI calls.

Keep the raw model trial and its completed revision-2 attempt as evidence. Never
apply this to a human course or silently repair the old attempt snapshot.
"""
import copy
import json
from pathlib import Path
import sqlite3

import httpx

from study_backend.ordering import derive_generated_ordering, verify_ordering

ROOT=Path(__file__).resolve().parents[2]


def main():
    target=ROOT/'backend/evidence/ordering-display-correction-trial.json'
    if target.exists():raise SystemExit('Keep the existing QA correction evidence; no repeated write sent.')
    trial=json.loads((ROOT/'backend/evidence/qwen9b-complete-contract-trial.json').read_text())
    if not trial['passed']:raise SystemExit('Require the completed self-authored Qwen QA trial.')
    report={'purpose':'Source-proved display-label correction on isolated Qwen QA course, not a second AI generation or Huy user trial',
            'passed':False,'ai_calls':0,'errors':[]}
    def save():target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    def call(client,method,path,body=None):
        response=client.request(method,'/api'+path,json=body);response.raise_for_status();return response.json()
    try:
        with httpx.Client(base_url='http://127.0.0.1:8770',timeout=20,trust_env=False) as client:
            client.cookies.update(json.loads((ROOT/'backend/runtime/qwen9b-complete-qa-session.json').read_text()))
            cid=trial['course_id'];base='/courses/'+cid;sid=trial['deterministic_roundtrip']['completion']['session_id']
            before=call(client,'GET',base+'/editor');old_attempt=call(client,'GET','/sessions/'+sid)
            if before['revision']!=2:raise RuntimeError('QA course changed; preserve it instead of replaying correction.')
            unit=before['content']['units'][0];questions=unit['data']['questions']
            index=next(i for i,q in enumerate(questions) if q['kind']=='ordering');original=questions[index]
            fragments=call(client,'GET',base+'/source-fragments?unit_id=unit-1')
            generated={k:v for k,v in original.items() if k not in {'answer','difficulty','difficulty_basis'}}
            cleaned,removed=derive_generated_ordering(generated,fragments)
            replacement={**original,'options':cleaned['options'],'answer':cleaned['answer']}
            if not removed or replacement['answer']!=original['answer']:raise RuntimeError('Only display labels may change in this trial.')
            verify_ordering(replacement,fragments)
            with sqlite3.connect('file:'+str(ROOT/'backend/runtime/study.sqlite3')+'?mode=ro',uri=True) as db:
                owner=db.execute('select owner_id from courses where id=?',(cid,)).fetchone()[0]
                usage_before=db.execute('select count(*) from ai_usage where owner_id=?',(owner,)).fetchone()[0]
            wallet=call(client,'GET','/wallet')
            report.update(course_id=cid,base_revision=2,original_question=original,replacement_question=replacement,
                          step_labels_removed=removed,old_attempt_id=sid);save()
            proposal=call(client,'POST',base+'/proposals',{'expected_revision':2,'unit_id':'unit-1','target':'question',
                'index':index,'request':'Ẩn số bước đang lộ đáp án; giữ nguyên cụm bước nguồn và đáp án theo vị trí nguồn.',
                'replacement':replacement})
            report['proposal_id']=proposal['proposal_id'];save()
            preview=call(client,'GET','/proposals/'+proposal['proposal_id'])
            if preview['before']!=original or preview['after']!=replacement:raise RuntimeError('Preview scope mismatch; do not apply.')
            unchanged=call(client,'GET',base+'/editor')
            if unchanged['revision']!=2 or unchanged['content']!=before['content']:raise RuntimeError('Preview unexpectedly changed the course.')
            applied=call(client,'POST','/proposals/'+proposal['proposal_id']+'/apply',{'expected_revision':2})
            report['applied_revision']=applied['revision'];save()
            after=call(client,'GET',base+'/editor');old_after=call(client,'GET','/sessions/'+sid)
            expected=copy.deepcopy(before['content']);expected['units'][0]['data']['questions'][index]=replacement
            if after['revision']!=3 or after['content']!=expected:raise RuntimeError('Correction changed an unrelated part.')
            if old_after['questions']!=old_attempt['questions'] or old_after['result']!=old_attempt['result']:
                raise RuntimeError('Completed attempt snapshot changed.')
            replay=client.post('/api/proposals/'+proposal['proposal_id']+'/apply',json={'expected_revision':2})
            if replay.status_code!=409:raise RuntimeError('Repeated apply was not rejected.')
            wallet_after=call(client,'GET','/wallet')
            with sqlite3.connect('file:'+str(ROOT/'backend/runtime/study.sqlite3')+'?mode=ro',uri=True) as db:
                usage_after=db.execute('select count(*) from ai_usage where owner_id=?',(owner,)).fetchone()[0]
            if usage_after!=usage_before or wallet_after!=wallet:raise RuntimeError('Manual correction changed AI usage or wallet.')
            report.update(passed=True,unrelated_content_unchanged=True,old_attempt_snapshot_unchanged=True,
                          old_attempt_score=old_after['result']['score'],repeat_apply_status=replay.status_code,
                          ai_usage_added=usage_after-usage_before,wallet_unchanged=True)
    except Exception as exc:
        report['errors'].append({'type':type(exc).__name__,'message':str(exc)[:1000]});raise
    finally:save();print(json.dumps({'passed':report['passed'],'evidence':str(target.relative_to(ROOT))}))


if __name__=='__main__':main()
