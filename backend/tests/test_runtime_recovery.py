import copy
import json
import os
from pathlib import Path
import signal
import socket
import sqlite3
import subprocess
import sys
import time
import unittest
from tempfile import TemporaryDirectory
from concurrent.futures import ThreadPoolExecutor

from fastapi import BackgroundTasks, HTTPException
from fastapi.testclient import TestClient
import httpx

from study_backend.app import create_app
from study_backend.runtime_lock import workspace_lock
from test_slice import FIXTURE_SOURCE, SliceFixture


class RuntimeRecoveryTests(SliceFixture):
    def test_queued_outline_reconciles_plan_and_repeated_startup_never_calls_provider(self):
        source=self.source();owner=self.client.post('/api/session').json()['id']
        with self.app.state.database.connection(write=True) as db:
            db.execute('INSERT INTO plans VALUES (?,?,?,?,?,?,?,?)',
                       ('interrupted-plan',owner,source['id'],'{}','{}','generating','fixture',None))
        jobs=self.app.state.jobs
        payload={'plan_id':'interrupted-plan','source_id':source['id']}
        async def unexpected(_):self.fail('Recovery called a provider')
        value=jobs.create(owner,'outline',payload,BackgroundTasks(),unexpected,jobs.identity(None,'outline',payload,owner))
        with self.app.state.database.connection(write=True) as db:
            db.execute('UPDATE jobs SET partial_json=? WHERE id=?',('{"saved":"checkpoint"}',value['job_id']))
        calls=self.provider.calls
        for _ in range(2):
            restarted=create_app(self.app.state.database.path,Path(self.temp.name)/'sources',provider=self.provider,economy_enabled=False)
            with TestClient(restarted,base_url='http://127.0.0.1',cookies=self.client.cookies) as client:
                job=client.get('/api/jobs/'+value['job_id']).json()
                self.assertEqual(job['status'],'failed');self.assertEqual(job['error']['code'],'SERVER_RESTARTED')
                self.assertEqual(job['partial'],{'saved':'checkpoint'})
                self.assertEqual(client.get('/api/plans/interrupted-plan').json()['status'],'failed')
        self.assertEqual(self.provider.calls,calls)

    def test_second_backend_cannot_mark_the_first_backends_active_job_as_failed(self):
        owner=self.client.post('/api/session').json()['id'];jobs=self.app.state.jobs
        async def unexpected(_):self.fail('Unstarted worker ran')
        payload={'message':'Not yet started'}
        first=create_app(self.app.state.database.path,Path(self.temp.name)/'sources',provider=self.provider,economy_enabled=False)
        with TestClient(first,base_url='http://127.0.0.1'):
            value=jobs.create(owner,'chat',payload,BackgroundTasks(),unexpected,jobs.identity(None,'chat',payload,owner))
            second=create_app(self.app.state.database.path,Path(self.temp.name)/'sources',provider=self.provider,economy_enabled=False)
            with self.assertRaisesRegex(RuntimeError,'backend khác'):
                with TestClient(second,base_url='http://127.0.0.1'): pass
            with self.app.state.database.connection() as db:
                self.assertEqual(db.execute('SELECT status FROM jobs WHERE id=?',(value['job_id'],)).fetchone()[0],'queued')

    def test_failed_startup_releases_lock_for_next_attempt(self):
        bad=create_app(self.app.state.database.path,Path(self.temp.name)/'sources',provider=self.provider,economy_enabled=False)
        def fail():raise RuntimeError('Fixture startup failed')
        bad.state.jobs.recover_interrupted=fail
        with self.assertRaisesRegex(RuntimeError,'Fixture startup failed'):
            with TestClient(bad,base_url='http://127.0.0.1'): pass
        with workspace_lock(self.app.state.database.path): pass


class ProcessRecoveryTests(unittest.TestCase):
    def test_sigkill_releases_lock_keeps_checkpoints_and_refunds_before_explicit_resume(self):
        """Real Uvicorn/HTTP/SQLite and SIGKILL; only inference is a double."""
        with TemporaryDirectory(prefix='study-process-recovery-') as directory:
            root=Path(directory);calls=root/'calls.jsonl';ready=root/'blocked'
            environment={**os.environ,'PYTHONPATH':str(Path('backend').resolve())+os.pathsep+str(Path('backend/tests').resolve()),
                         'STUDY_TEST_DB':str(root/'test.sqlite3'),'STUDY_TEST_SOURCES':str(root/'sources'),
                         'STUDY_TEST_CALLS':str(calls),'STUDY_TEST_READY':str(ready),'STUDY_TEST_BLOCK':'matching'}
            with socket.socket() as channel:
                channel.bind(('127.0.0.1',0));port=channel.getsockname()[1]
            processes=[]
            def start():
                process=subprocess.Popen([sys.executable,'-m','uvicorn','process_recovery_fixture:app','--host','127.0.0.1','--port',str(port),'--log-level','error'],env=environment,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                processes.append(process)
                deadline=time.monotonic()+8
                while time.monotonic()<deadline:
                    if process.poll() is not None:self.fail('Isolated fixture server failed to start')
                    try:
                        if httpx.get(f'http://127.0.0.1:{port}/',timeout=.3,trust_env=False).status_code==200:return process
                    except httpx.TransportError:pass
                    time.sleep(.03)
                self.fail('Isolated fixture server startup timed out')
            def wait(client,jid,blocked=False):
                deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    job=client.get('/api/jobs/'+jid).json()
                    if blocked and ready.exists():return job
                    if not blocked and job['status'] in {'succeeded','failed','cancelled'}:return job
                    time.sleep(.02)
                self.fail('Bounded fixture job did not reach expected checkpoint')
            def paid(client,path,body,key):
                headers={'Idempotency-Key':key}
                quote=client.post(path,json=body,headers=headers)
                self.assertEqual(quote.status_code,402,quote.text)
                headers['Coin-Quote-Id']=quote.json()['detail']['quote_id']
                response=client.post(path,json=body,headers=headers);response.raise_for_status()
                return response.json()['job_id'],headers
            try:
                original=start()
                with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=3,trust_env=False) as client:
                    client.post('/api/session').raise_for_status()
                    source=client.post('/api/sources/text',json={'name':'crash-test.txt','text':FIXTURE_SOURCE.decode()}).json()
                    source=client.post('/api/sources/'+source['id']+'/review',json={'expected_revision':1,'texts':[f['text'] for f in source['fragments']]}).json()
                    plan_job,_=paid(client,'/api/plans',{'source_id':source['id'],'subject':'Mạng máy tính','goal':'Học network','language':'vi','fragment_ids':[f['id'] for f in source['fragments']]},'plan')
                    plan=wait(client,plan_job);self.assertEqual(plan['status'],'succeeded',plan)
                    approved=client.post('/api/plans/'+plan['result']['plan_id']+'/approve',json={'expected_revision':1}).json();cid=approved['course_id']
                    path='/api/courses/'+cid+'/generate';body={'expected_revision':1,'unit_id':'unit-1'}
                    jid,headers=paid(client,path,body,'lesson-before-crash')
                    before=wait(client,jid,blocked=True)
                    self.assertIn('reading',before['partial']);self.assertEqual(set(before['partial']['questions']),{'mcq','cloze'})
                    self.assertEqual(client.get('/api/wallet').json()['held'],6)
                    original.send_signal(signal.SIGKILL);original.wait(timeout=5)
                    call_count=len(calls.read_text().splitlines())
                    environment['STUDY_TEST_BLOCK']=''
                    start()
                    after=client.get('/api/jobs/'+jid).json()
                    self.assertEqual(after['status'],'failed');self.assertEqual(after['error']['code'],'SERVER_RESTARTED')
                    self.assertEqual(after['partial'],before['partial'])
                    self.assertEqual(client.get('/api/wallet').json()['held'],0)
                    self.assertEqual(client.get('/api/wallet').json()['balance'],17)
                    self.assertEqual(len(calls.read_text().splitlines()),call_count)
                    replay=client.post(path,json=body,headers=headers).json()
                    self.assertEqual(replay,{'job_id':jid});self.assertEqual(len(calls.read_text().splitlines()),call_count)
                    resumed_id,_=paid(client,path,{**body,'resume_job_id':jid},'lesson-after-crash')
                    resumed=wait(client,resumed_id);self.assertEqual(resumed['status'],'succeeded',resumed)
                    new_calls=[json.loads(line)['schema'] for line in calls.read_text().splitlines()[call_count:]]
                    self.assertEqual(new_calls,['MatchingDraft','OrderingDraft','ShortAnswerDraft'])
                    self.assertEqual(resumed['partial']['reading'],before['partial']['reading'])
                    self.assertEqual(resumed['partial']['questions']['mcq'],before['partial']['questions']['mcq'])
                    self.assertEqual(client.get('/api/wallet').json()['balance'],14)
                    self.assertEqual(client.get('/api/wallet').json()['held'],0)
                    self.assertEqual(client.get('/api/courses/'+cid).json()['revision'],2)
                    # Initial extraction is not an AI job. Crash while its
                    # parsing row exists, then prove it can be managed again.
                    calls_before_native=len(calls.read_text().splitlines())
                    processes[-1].terminate();processes[-1].wait(timeout=5)
                    environment['STUDY_TEST_BLOCK']='source';ready.unlink(missing_ok=True)
                    parsing_process=start()
                    with ThreadPoolExecutor(1) as pool:
                        upload=pool.submit(client.post,'/api/sources/upload',files={'file':('interrupted.txt',FIXTURE_SOURCE,'text/plain')})
                        deadline=time.monotonic()+3
                        while not ready.exists() and time.monotonic()<deadline:time.sleep(.02)
                        self.assertTrue(ready.exists())
                        with sqlite3.connect(root/'test.sqlite3') as db:
                            sid=db.execute("select id from sources where status='parsing'").fetchone()[0]
                        parsing_process.send_signal(signal.SIGKILL);parsing_process.wait(timeout=5)
                        with self.assertRaises(httpx.TransportError):upload.result(timeout=3)
                    environment['STUDY_TEST_BLOCK']='';start()
                    source=client.get('/api/sources/'+sid).json()
                    self.assertEqual(source['status'],'failed');self.assertEqual(source['revision'],0)
                    self.assertEqual(source['metadata']['extraction_interrupted']['code'],'SERVER_RESTARTED')
                    self.assertEqual(client.get('/api/sources/'+sid+'/original').content,FIXTURE_SOURCE)
                    client.request('DELETE','/api/sources/'+sid,json={'expected_revision':0,'expected_lifecycle_version':0}).raise_for_status()
                    client.post('/api/sources/'+sid+'/restore',json={'expected_revision':0,'expected_lifecycle_version':1}).raise_for_status()
                    retried=client.post('/api/sources/'+sid+'/retry-extraction',json={'expected_revision':0})
                    retried.raise_for_status();self.assertEqual(retried.json()['revision'],1)
                    self.assertTrue(retried.json()['fragments'])
                    self.assertEqual(client.get('/api/courses/'+cid).json()['revision'],2)
                    self.assertEqual(client.get('/api/wallet').json()['balance'],14)
                    self.assertEqual(len(calls.read_text().splitlines()),calls_before_native)
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.terminate()
                        try:process.wait(timeout=5)
                        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
