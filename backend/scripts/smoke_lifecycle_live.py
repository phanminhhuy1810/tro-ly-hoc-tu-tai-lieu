"""Actual loopback HTTP deletion/restoration on a new, explicitly labelled QA profile.

No human data deletion. One bounded real local lesson over a self-authored
networking fixture supports the sharing/history checks; not a quality benchmark.
"""
import hashlib
import json
import sys
import time
from pathlib import Path

import httpx

ROOT=Path(__file__).resolve().parents[2]
BASE='http://127.0.0.1:8770/api'


def run():
    evidence=ROOT/'backend/evidence/lifecycle-live-trial.json'
    session_file=ROOT/'backend/runtime/lifecycle-qa-session.json'
    reference_fix='--retry-after-reference-codec' in sys.argv
    after_fix='--retry-after-prompt-fix' in sys.argv or reference_fix
    if evidence.exists():
        if not after_fix:raise SystemExit('Keep existing evidence; this probe does not repeat automatically.')
        baseline=ROOT/('backend/evidence/lifecycle-lesson-failure-after-prompt.json' if reference_fix else 'backend/evidence/lifecycle-lesson-failure-before.json')
        if baseline.exists():raise SystemExit('The one explicit after-fix run has already started; inspect evidence instead of looping.')
        old=json.loads(evidence.read_text())
        assert old.get('all_passed') is False and old['generation_job']['status']=='failed'
        evidence.rename(baseline)
    if session_file.exists() and '--resume-initial-profile' not in sys.argv and not after_fix:
        raise SystemExit('Existing QA setup detected; inspect it before explicitly continuing.')
    checks={};report={'purpose':__doc__,'fixture':'experiments/05-office-inputs/fixtures/network-notes.txt','checks':checks}
    if after_fix:report['baseline_failure_file']='backend/evidence/lifecycle-lesson-failure-before.json'
    if reference_fix:report['second_failure_file']='backend/evidence/lifecycle-lesson-failure-after-prompt.json'
    raw=(ROOT/report['fixture']).read_bytes();digest=hashlib.sha256(raw).hexdigest()
    with httpx.Client(base_url=BASE,timeout=15,trust_env=False) as creator,httpx.Client(base_url=BASE,timeout=15,trust_env=False) as learner:
        continuing=session_file.exists()
        if continuing:
            private=json.loads(session_file.read_text());creator.cookies.set('study_session',private['study_session'])
        owner=creator.post('/session');owner.raise_for_status();owner=owner.json()['id']
        peer=learner.post('/session');peer.raise_for_status()
        private={'owner_id':owner,'study_session':creator.cookies.get('study_session')}
        session_file.touch(mode=0o600);session_file.write_text(json.dumps(private)+'\n')
        def request(client,method,path,**kwargs):
            response=client.request(method,path,**kwargs);response.raise_for_status();return response.json()
        def state(kind,rid):return request(creator,'GET',f'/{kind}s/{rid}/lifecycle')
        def transition(kind,rid,restore=False):
            current=state(kind,rid)
            return request(creator,'POST' if restore else 'DELETE',f'/{kind}s/{rid}'+('/restore' if restore else ''),json={
                'expected_revision':current['revision'],'expected_lifecycle_version':current['lifecycle_version']})
        if continuing:
            courses=request(creator,'GET','/courses');assert len(courses)==1
            cid=courses[0]['id'];plan=request(creator,'GET','/plans/'+courses[0]['plan_id'])
            sid=plan['source_id'];source=request(creator,'GET','/sources/'+sid)
            report['initial_probe_failure']={'status':409,'step':'publication-preview before any lesson existed',
                'message':'Tạo và xem lại ít nhất một phần trước khi chia sẻ.','classification':'Expected business guard; original harness lacked a ready lesson.'}
        else:
            source=request(creator,'POST','/sources/upload',files={'file':('QA lifecycle — network.txt',raw,'text/plain')})
            sid=source['id'];source=request(creator,'POST','/sources/'+sid+'/review',json={'expected_revision':1,'texts':[f['text'] for f in source['fragments']]})
            plan=request(creator,'POST','/plans/from-source-sections',json={'source_id':sid,'expected_extraction_revision':2,
                'subject':'Mạng máy tính · QA vòng đời','goal':'Hiểu IPv4 và subnet /26','language':'vi',
                'fragment_ids':[f['id'] for f in source['fragments']]})
            approved=request(creator,'POST','/plans/'+plan['id']+'/approve',json={'expected_revision':1});cid=approved['course_id']
        course=request(creator,'GET','/courses/'+cid+'/editor');unit=course['content']['units'][0]
        assert not unit['data'],'This script does not regenerate a ready unit.'
        if not after_fix:
            request(creator,'PUT','/ai/selection',json={'model_id':'local:gemma4:12b-mlx','expected_revision':0,'allow_external':False})
            proposal=request(creator,'POST','/courses/'+cid+'/future-plan-preview',json={'expected_revision':course['revision'],
                'units':[{'unit_id':unit['id'],'title':'QA IPv4 và subnet /26','objective':'Hiểu 32 bit IPv4, 6 bit host của /26 và network/broadcast trong ví dụ nguồn.',
                          'source_refs':[f['id'] for f in source['fragments'][:6]]}],
                'preferences':{'subject':'Mạng máy tính','goal':'Hiểu IPv4, network, broadcast và host trong /26','question_types':['mcq'],'question_count':1,'card_count':1},
                'request':'QA: chỉ tạo một phần đọc và một câu trắc nghiệm bám nguồn, tránh đáp án nhiễu tương đương đơn vị.'})
            applied=request(creator,'POST','/proposals/'+proposal['proposal_id']+'/apply',json={'expected_revision':course['revision']})
        else:applied={'revision':course['revision']}
        job_key='lifecycle-one-local-lesson-v16' if reference_fix else 'lifecycle-one-local-lesson-v15' if after_fix else 'lifecycle-one-local-lesson'
        job_result=request(creator,'POST','/courses/'+cid+'/generate',json={'expected_revision':applied['revision'],'unit_id':unit['id']},headers={'Idempotency-Key':job_key})
        deadline=time.monotonic()+230
        while time.monotonic()<deadline:
            job=request(creator,'GET','/jobs/'+job_result['job_id'])
            if job['status'] in {'succeeded','failed','cancelled'}:break
            time.sleep(.25)
        report['generation_job']=job
        if job['status']!='succeeded':
            report.update(all_passed=False,failure='Bounded real lesson failed; kept partial, did not retry or publish.')
            evidence.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
            raise SystemExit('Local lesson did not complete; failure and partial saved, no automatic retry.')
        original_course=request(creator,'GET','/courses/'+cid+'/editor')
        revision=original_course['revision'];question=original_course['content']['units'][0]['data']['questions'][0]
        attempt=request(creator,'POST','/courses/'+cid+'/sessions',json={'expected_revision':revision,'unit_id':unit['id']})
        request(creator,'POST','/sessions/'+attempt['id']+'/answers',json={'item_id':attempt['questions'][0]['id'],'answer':question['answer']})
        request(creator,'POST','/sessions/'+attempt['id']+'/complete')
        old_session=request(creator,'GET','/sessions/'+attempt['id'])
        # Completion changes only this user's progress, not content.
        original_course=request(creator,'GET','/courses/'+cid+'/editor')
        wallet=request(creator,'GET','/wallet')
        publication=request(creator,'POST','/courses/'+cid+'/publication-preview',json={'expected_revision':revision,'visibility':'public','share_original':True})
        request(creator,'POST','/publications/'+publication['publication_id']+'/apply',json={'expected_revision':revision})
        request(learner,'POST','/courses/'+cid+'/enroll')
        code=request(creator,'POST','/courses/'+cid+'/invite')['code']
        checks['learner_initially_has_original']=hashlib.sha256(learner.get('/sources/'+sid+'/original').content).hexdigest()==digest
        blocked=creator.request('DELETE','/sources/'+sid,json={'expected_revision':2,'expected_lifecycle_version':0})
        checks['active_course_protects_source']=blocked.status_code==409 and blocked.json()['detail']['code']=='RESOURCE_DEPENDENCIES'
        deleted_course=transition('course',cid)
        checks['course_unavailable_to_both']=all(c.get('/courses/'+cid).status_code==404 for c in (creator,learner))
        checks['original_sharing_revoked']=learner.get('/sources/'+sid+'/original').status_code==404
        checks['community_unavailable']=learner.get('/community/'+cid).status_code==404
        deleted_source=transition('source',sid)
        checks['creator_original_unavailable_in_trash']=creator.get('/sources/'+sid+'/original').status_code==404
        trash=request(creator,'GET','/trash');checks['two_private_trash_items']=trash['total']==2 and request(learner,'GET','/trash')['total']==0
        checks['old_session_retained_in_trash']=request(creator,'GET','/sessions/'+attempt['id'])==old_session
        waiting=creator.post('/courses/'+cid+'/restore',json={'expected_revision':revision,'expected_lifecycle_version':deleted_course['lifecycle_version']})
        checks['restore_requires_source_first']=waiting.status_code==409
        restored_source=transition('source',sid,True)
        checks['exact_original_restored']=hashlib.sha256(creator.get('/sources/'+sid+'/original').content).hexdigest()==digest
        restored_course=transition('course',cid,True)
        checks['course_snapshot_unchanged']=request(creator,'GET','/courses/'+cid+'/editor')==original_course
        checks['old_session_retained_after_restore']=request(creator,'GET','/sessions/'+attempt['id'])==old_session
        checks['restored_course_stays_private']=learner.get('/courses/'+cid).status_code==404 and learner.post('/community/join',json={'code':code}).status_code==404
        checks['trash_empty_after_restore']=request(creator,'GET','/trash')['total']==0
        after_wallet=request(creator,'GET','/wallet');checks['wallet_unchanged']=after_wallet==wallet
        report.update(owner_id=owner,learner_id=peer.json()['id'],source_id=sid,source_sha256=digest,course_id=cid,
                      source_deleted_version=deleted_source['lifecycle_version'],source_restored_version=restored_source['lifecycle_version'],
                      course_deleted_version=deleted_course['lifecycle_version'],course_restored_version=restored_course['lifecycle_version'],
                      remaining_qa_course_state='private, restored; one real Gemma lesson and a completed QA attempt',wallet=after_wallet,
                      all_passed=all(checks.values()))
    evidence.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'all_passed':report['all_passed'],'checks':checks},ensure_ascii=False))
    if not report['all_passed']:raise SystemExit(1)


if __name__=='__main__':run()
