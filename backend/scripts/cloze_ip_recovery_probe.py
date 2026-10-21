"""Explicit one-run recovery on an isolated DB copy, using the failed job's model.

No provider default, live course/history, live Coin or source is changed.
The local model is real; this is a development case, not held-out evaluation.
"""
import hashlib
import json
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from study_backend.ai import LocalAI
from study_backend.app import create_app
from study_backend.generation_contract import GENERATION_PROCESSOR_VERSION, validated_generation
from study_backend.models import QUESTION_DRAFTS, grade
from study_backend.providers import Choice, ProviderRegistry

ROOT=Path(__file__).resolve().parents[2]
ORIGINAL_JOB='3773b30bc8e949f6b8f6489ed0b8d840'


def run():
    live=sqlite3.connect(f'file:{ROOT}/backend/runtime/study.sqlite3?mode=ro',uri=True)
    live.row_factory=sqlite3.Row
    if live.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]:
        raise SystemExit('A live job is active; did not run the probe.')
    old=dict(live.execute('SELECT * FROM jobs WHERE id=?',(ORIGINAL_JOB,)).fetchone())
    payload=json.loads(old['payload_json']);partial=json.loads(old['partial_json'])
    course=payload['course_id'];owner=old['owner_id'];model=payload['_provider']['model']
    choice=payload['_provider']['model_choice_id']
    assert model=='gemma4:12b-mlx' and choice=='local:gemma4:12b-mlx'
    copy=ROOT/'backend/runtime/cloze-ip-recovery-qa.sqlite3'
    if copy.exists():raise SystemExit('QA copy already exists; keep prior evidence and choose an explicit new run.')
    copy.touch(mode=0o600);qa=sqlite3.connect(copy);live.backup(qa)
    token=secrets.token_urlsafe(32)
    qa.execute('INSERT INTO auth_sessions VALUES (?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),owner,int(time.time())+3600,datetime.now(timezone.utc).isoformat()))
    qa.commit();qa.close()

    calls=[]
    class ObservedLocal(LocalAI):
        async def generate_stream(self,schema,instruction,fragments,progress):
            calls.append(schema.__name__)
            return await super().generate_stream(schema,instruction,fragments,progress)
    ai=ObservedLocal();ai.model=model
    registry=ProviderRegistry([Choice(choice,model,ai)],choice)
    app=create_app(copy,ROOT/'backend/runtime/sources',provider_registry=registry,economy_enabled=False)
    report={'purpose':'Bounded real-model recovery in a private SQLite copy, not a production course mutation',
            'original_job_id':ORIGINAL_JOB,'model':model,'processor_version':GENERATION_PROCESSOR_VERSION,
            'live_database_mutated':False,'live_coin_changed':False,'automatic_retries':0}
    start=time.monotonic()
    with TestClient(app,base_url='http://127.0.0.1') as client:
        client.cookies.set('study_session',token)
        response=client.post(f'/api/courses/{course}/generate',json={
            'expected_revision':payload['expected_revision'],'unit_id':payload['unit_id'],'resume_job_id':ORIGINAL_JOB})
        response.raise_for_status()
        job=client.get('/api/jobs/'+response.json()['job_id']).json()
        report.update(job=job,elapsed_seconds=round(time.monotonic()-start,3),new_model_stages=calls,
                      reading_reused=job['partial'].get('reading')==partial['reading'],
                      mcq_reused=job['partial'].get('questions',{}).get('mcq')==partial['questions']['mcq'])
        if job['status']=='succeeded':
            current=client.get(f'/api/courses/{course}/editor').json()
            unit=next(u for u in current['content']['units'] if u['id']==payload['unit_id'])
            report['lesson']=unit['data'];report['coverage']=unit['generation']['question_coverage']
            session=client.post(f'/api/courses/{course}/sessions',json={'expected_revision':current['revision'],'unit_id':unit['id']})
            session.raise_for_status();session=session.json();checks=[]
            for item, question in zip(session['questions'],unit['data']['questions']):
                graded=client.post(f"/api/sessions/{session['id']}/answers",json={'item_id':item['id'],'answer':question['answer']})
                graded.raise_for_status();checks.append({'kind':question['kind'],'correct':graded.json()['correct'],'grading':graded.json().get('grading')})
            report['practice_checks']=checks
            completed=client.post(f"/api/sessions/{session['id']}/complete")
            completed.raise_for_status();report['practice_result']=completed.json()
    original_after=dict(live.execute('SELECT * FROM jobs WHERE id=?',(ORIGINAL_JOB,)).fetchone())
    report['original_failed_job_unchanged']=original_after==old
    report['live_course_revision']=live.execute('SELECT active_revision FROM courses WHERE id=?',(course,)).fetchone()[0]
    live.close()
    (ROOT/'backend/evidence/cloze-ip-recovery-real.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('model','elapsed_seconds','new_model_stages','reading_reused','mcq_reused','original_failed_job_unchanged','live_course_revision')},ensure_ascii=False))
    print('status',job['status'],'error',job.get('error'))
    if report.get('coverage'):print('coverage',json.dumps(report['coverage'],ensure_ascii=False))


if __name__=='__main__':run()
