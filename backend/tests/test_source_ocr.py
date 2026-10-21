"""Native OCR lifecycle with explicit reader doubles; real native probes are separate."""
import asyncio
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock,patch

from fastapi.testclient import TestClient
import httpx
from PIL import Image

from study_backend.app import create_app
from study_backend.extract import extract
from study_backend.native_ocr import decode_scope,run_native
from test_pdf_recovery import pdf_bytes
from test_office_inputs import word_fixture
from test_slice import TestProvider


def reading(text):
    return {'text':text,'observations':[{'text':text,'bounds':[.1,.2,.3,.4],'recognizer_score':.9}] if text else [],
            'engine':'explicit_native_reader_double','revision':1}


class SourceOCRTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.root=Path(self.tmp.name);self.calls=[];self.initial_pages=20
        self.provider=TestProvider();self.provider.enabled=False
        async def reader(path,kind,item,**options):
            self.calls.append(item['key']);return reading('OCR '+item['key'])
        async def frame_counter(path):return 47
        self.reader,self.frames=reader,frame_counter
        self.app=self.make_app();self.client=TestClient(self.app,base_url='http://127.0.0.1');self.client.post('/api/session').raise_for_status()

    def make_app(self):
        return create_app(self.root/'data.sqlite',self.root/'sources',self.provider,extractor=self.extractor,
                          native_ocr_reader=self.reader,native_frame_counter=self.frames)

    def extractor(self,name,raw):
        fragments,warnings=extract(name,raw,ocr=False)
        if name.endswith('.pdf'):
            fragments += [{'text':f'Previously read page {page}','locator':{'type':'ocr_page','page':page,'extraction_method':'ocr_supplement'},
                           'needs_review':True,'provenance':{'kind':'ocr_supplement'}} for page in range(1,self.initial_pages+1)]
        return fragments,warnings

    def tearDown(self):self.client.close();self.tmp.cleanup()

    def source(self,count=47):
        raw=pdf_bytes(count=count,images=tuple(range(1,count+1)))
        response=self.client.post('/api/sources/upload',files={'file':('scan.pdf',raw)});response.raise_for_status()
        return response.json(),raw

    def batch(self,source,items=None,key=None):
        body={'expected_revision':source['revision']}
        if items is not None:body['items']=items
        response=self.client.post('/api/sources/'+source['id']+'/ocr-batches',json=body,headers={'Idempotency-Key':key} if key else {})
        response.raise_for_status();job=self.client.get('/api/jobs/'+response.json()['job_id']).json()
        self.assertEqual(job['status'],'succeeded',job)
        value=self.client.get('/api/ocr-batches/'+job['result']['ocr_batch_id']).json()
        return value,response.json(),job

    def action(self,batch,source_revision=None):
        return {'expected_revision':batch['base_revision'] if source_revision is None else source_revision,'expected_batch_version':batch['version']}

    def test_continuation_skips_existing_twenty_and_preserves_source_until_apply_without_ai_or_coin(self):
        source,raw=self.source();path='/api/sources/'+source['id'];wallet=self.client.get('/api/wallet').json()
        status=self.client.get(path+'/ocr-status').json();self.assertEqual(status['next_items'],['page:'+str(i) for i in range(21,41)])
        batch,start,job=self.batch(source,key='first-pass')
        self.assertEqual(self.calls,['page:'+str(i) for i in range(21,41)])
        self.assertEqual(self.client.get(path).json()['revision'],1);self.assertEqual(batch['completed_count'],20)
        self.assertEqual(job['provider']['model'],'native_ocr');self.assertEqual(self.provider.calls,0)
        self.assertEqual(self.client.get('/api/wallet').json(),wallet)
        with self.app.state.database.connection() as db:self.assertEqual(db.execute('SELECT count(*) FROM ai_usage').fetchone()[0],0)
        updated=self.client.post('/api/ocr-batches/'+batch['id']+'/apply',json=self.action(batch));updated.raise_for_status();updated=updated.json()
        self.assertFalse(updated['reviewed']);self.assertEqual(updated['revision'],2)
        self.assertEqual(self.client.get(path+'?revision=1').json()['fragments'],source['fragments'])
        self.assertEqual(self.client.get(path+'/original').content,raw)
        replay=self.client.post(path+'/ocr-batches',json={'expected_revision':1},headers={'Idempotency-Key':'first-pass'})
        self.assertEqual(replay.json(),start);self.assertEqual(len(self.calls),20)
        replay_apply=self.client.post('/api/ocr-batches/'+batch['id']+'/apply',json=self.action(batch));self.assertEqual(replay_apply.json()['revision'],2)
        second,_,_=self.batch(updated);self.assertEqual(second['completed_count'],7)
        self.assertEqual(self.calls,['page:'+str(i) for i in range(21,48)])

    def test_saved_manual_draft_is_protected_and_does_not_claim_source_review(self):
        source,_=self.source();path='/api/sources/'+source['id']
        texts=[f['text'] if f['locator'].get('page')!=24 else 'Manual correction on page 24' for f in source['fragments']]
        saved=self.client.post(path+'/save-draft',json={'expected_revision':1,'texts':texts});saved.raise_for_status();saved=saved.json()
        self.assertFalse(saved['reviewed']);self.assertEqual(saved['status'],'needs_review')
        status=self.client.get(path+'/ocr-status').json();p24=next(i for i in status['items'] if i['key']=='page:24')
        self.assertEqual(p24['state'],'protected')
        self.assertEqual(self.client.post(path+'/ocr-batches',json={'expected_revision':2,'items':['page:24']}).status_code,422)
        batch,_,_=self.batch(saved,['page:23','page:25'])
        result=self.client.post('/api/ocr-batches/'+batch['id']+'/apply',json=self.action(batch)).json()
        self.assertEqual(next(f['text'] for f in result['fragments'] if f['locator']['page']==24),'Manual correction on page 24')
        self.assertEqual(self.calls,['page:23','page:25'])

    def test_stale_results_rebase_without_rereading_and_skip_new_manual_scope(self):
        source,_=self.source();path='/api/sources/'+source['id'];batch,_,_=self.batch(source,['page:21','page:22','page:23'])
        texts=[f['text'] if f['locator'].get('page')!=22 else 'New manual page 22' for f in source['fragments']]
        self.client.post(path+'/save-draft',json={'expected_revision':1,'texts':texts}).raise_for_status()
        self.assertEqual(self.client.post('/api/ocr-batches/'+batch['id']+'/apply',json=self.action(batch,2)).status_code,409)
        response=self.client.post('/api/ocr-batches/'+batch['id']+'/rebase-preview',json=self.action(batch,2));response.raise_for_status();child=response.json()
        self.assertEqual(child['skipped_protected_or_existing_items'],['page:22']);self.assertEqual(child['completed_count'],2)
        self.assertEqual(self.client.get('/api/ocr-batches/'+batch['id']).json()['state'],'superseded')
        response=self.client.post('/api/ocr-batches/'+child['id']+'/apply',json=self.action(child));response.raise_for_status()
        self.assertEqual(self.calls,['page:21','page:22','page:23'])
        self.assertEqual(next(f['text'] for f in response.json()['fragments'] if f['locator']['page']==22),'New manual page 22')

    def test_empty_detection_is_reported_not_called_blank_or_retried_automatically(self):
        async def empty(path,kind,item,**options):self.calls.append(item['key']);return reading('')
        self.app.state.source_ocr.reader=empty;source,_=self.source();batch,_,_=self.batch(source,['page:21'])
        self.assertEqual(batch['no_text_count'],1)
        response=self.client.post('/api/ocr-batches/'+batch['id']+'/apply',json=self.action(batch));response.raise_for_status()
        status=self.client.get('/api/sources/'+source['id']+'/ocr-status').json()
        self.assertEqual(next(i['state'] for i in status['items'] if i['key']=='page:21'),'no_text_detected')
        self.assertNotIn('page:21',status['next_items']);self.assertTrue(status['text_detection_is_not_accuracy_verification'])

    def test_long_page_does_not_duplicate_full_observations_in_each_fragment(self):
        text='Native observation '*400
        async def long_page(path,kind,item,**options):return reading(text)
        self.app.state.source_ocr.reader=long_page;source,_=self.source()
        batch,_,_=self.batch(source,['page:21'])
        response=self.client.post('/api/ocr-batches/'+batch['id']+'/apply',json=self.action(batch));response.raise_for_status()
        added=[f for f in response.json()['fragments'] if f.get('provenance',{}).get('batch_id')==batch['id']]
        self.assertEqual(''.join(f['text'] for f in added),text.strip())
        self.assertLessEqual(sum(len(o['text']) for f in added for o in f['locator']['ocr_observations']),len(text))
        self.assertTrue(all(o['bounds_cover_full_observation'] for f in added for o in f['locator']['ocr_observations']))

    def test_retries_are_explicit_and_bounded_and_cannot_change_original(self):
        async def failed(path,kind,item,**options):self.calls.append(item['key']);raise ValueError('Explicit reader failure')
        self.app.state.source_ocr.reader=failed;source,raw=self.source();batch,_,_=self.batch(source,['page:21'])
        self.assertEqual(batch['status'],'attention_required')
        response=self.client.post('/api/ocr-batches/'+batch['id']+'/resume',json=self.action(batch));response.raise_for_status()
        refreshed=self.client.get('/api/ocr-batches/'+batch['id']).json()
        self.assertEqual(refreshed['results']['page:21']['attempts'],2)
        self.assertEqual(self.client.post('/api/ocr-batches/'+batch['id']+'/resume',json=self.action(refreshed)).status_code,422)
        self.assertEqual(self.client.post('/api/ocr-batches/'+batch['id']+'/apply',json=self.action(refreshed)).status_code,422)
        self.assertEqual(self.client.get('/api/sources/'+source['id']+'/original').content,raw);self.assertEqual(len(self.calls),2)

    def test_office_and_multiframe_sources_continue_after_twenty(self):
        self.initial_pages=0
        raw=word_fixture(image_only=True)
        response=self.client.post('/api/sources/upload',files={'file':('image-only.docx',raw)});self.assertEqual(response.status_code,422)
        sid=response.json()['detail']['source_id'];source=self.client.get('/api/sources/'+sid).json()
        status=self.client.get('/api/sources/'+sid+'/ocr-status').json();self.assertEqual(status['kind'],'asset')
        batch,_,_=self.batch(source);response=self.client.post('/api/ocr-batches/'+batch['id']+'/apply',json=self.action(batch));response.raise_for_status()
        self.assertEqual(response.json()['revision'],1);self.assertTrue(response.json()['fragments'][0]['locator']['asset_id'])
        frames=[Image.new('RGB',(20,20),'white') for _ in range(47)];out=BytesIO();frames[0].save(out,format='TIFF',save_all=True,append_images=frames[1:])
        response=self.client.post('/api/sources/upload',files={'file':('frames.tiff',out.getvalue())});self.assertEqual(response.status_code,422)
        sid=response.json()['detail']['source_id'];source=self.client.get('/api/sources/'+sid).json()
        status=self.client.get('/api/sources/'+sid+'/ocr-status').json();self.assertEqual(status['total_items'],47)
        batch,_,_=self.batch(source,['frame:21','frame:47']);self.assertEqual(batch['completed_count'],2)
        response=self.client.post('/api/ocr-batches/'+batch['id']+'/apply',json=self.action(batch));response.raise_for_status()
        self.assertEqual([f['locator']['frame'] for f in response.json()['fragments']],[21,47])

    def test_foreign_access_and_malformed_scope_do_not_reach_reader(self):
        source,_=self.source();path='/api/sources/'+source['id']
        self.assertEqual(self.client.post(path+'/ocr-batches',json={'expected_revision':1,'items':['page:21','page:21']}).status_code,422)
        self.assertEqual(self.client.post(path+'/ocr-batches',json={'expected_revision':1,'items':['page:1001']}).status_code,422)
        batch,_,_=self.batch(source,['page:21']);calls=len(self.calls)
        with TestClient(self.app,base_url='http://127.0.0.1') as foreign:
            foreign.post('/api/session')
            self.assertEqual(foreign.get(path+'/ocr-status').status_code,404)
            self.assertEqual(foreign.get('/api/ocr-batches/'+batch['id']).status_code,404)
            self.assertEqual(foreign.get('/api/ocr-batches/'+batch['id']+'/items/page:21/image').status_code,404)
            for action in ['resume','apply','discard','rebase-preview']:
                self.assertEqual(foreign.post('/api/ocr-batches/'+batch['id']+'/'+action,json=self.action(batch)).status_code,404)
        self.assertEqual(len(self.calls),calls)

    def test_cancel_and_restart_keep_checkpoint_and_resume_only_unfinished_item(self):
        source,_=self.source()
        async def scenario():
            blocked=asyncio.Event()
            async def reader(path,kind,item,**options):
                self.calls.append(item['key'])
                if item['key']=='page:22':blocked.set();await asyncio.Event().wait()
                return reading('Completed '+item['key'])
            self.app.state.source_ocr.reader=reader
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://127.0.0.1',cookies=self.client.cookies) as client:
                pending=asyncio.create_task(client.post('/api/sources/'+source['id']+'/ocr-batches',json={'expected_revision':1,'items':['page:21','page:22']}))
                await asyncio.wait_for(blocked.wait(),3)
                with self.app.state.database.connection() as db:job_id=db.execute("SELECT id FROM jobs WHERE task='source_ocr'").fetchone()[0]
                await client.post('/api/jobs/'+job_id+'/cancel',json={});await asyncio.wait_for(pending,3)
                job=(await client.get('/api/jobs/'+job_id)).json();batch_id=job['context']['ocr_batch_id']
                batch=(await client.get('/api/ocr-batches/'+batch_id)).json();self.assertEqual(batch['completed_count'],1)
                self.assertEqual((await client.get('/api/sources/'+source['id'])).json()['revision'],1)
                return batch_id,job_id
        batch_id,job_id=asyncio.run(scenario())
        # Simulate a persisted interrupted worker only after the original handle stopped.
        with self.app.state.database.connection(write=True) as db:db.execute("UPDATE jobs SET status='running' WHERE id=?",(job_id,))
        restarted=self.make_app()
        with TestClient(restarted,base_url='http://127.0.0.1') as client:
            client.cookies.update(self.client.cookies)
            batch=client.get('/api/ocr-batches/'+batch_id).json();self.assertEqual(batch['job_status'],'failed')
            self.assertEqual(batch['completed_count'],1)
            response=client.post('/api/ocr-batches/'+batch_id+'/resume',json=self.action(batch));response.raise_for_status()
            complete=client.get('/api/ocr-batches/'+batch_id).json();self.assertEqual(complete['completed_count'],2)
        self.assertEqual(self.calls,['page:21','page:22','page:22'])

    def test_cancelled_reader_cannot_commit_even_if_it_ignores_cancellation(self):
        source,_=self.source()
        async def scenario():
            started=asyncio.Event()
            async def late(path,kind,item,**options):
                started.set()
                try:await asyncio.Event().wait()
                except asyncio.CancelledError:return reading('Late result must not be committed')
            self.app.state.source_ocr.reader=late
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://127.0.0.1',cookies=self.client.cookies) as client:
                pending=asyncio.create_task(client.post('/api/sources/'+source['id']+'/ocr-batches',json={'expected_revision':1,'items':['page:21']}))
                await asyncio.wait_for(started.wait(),2)
                with self.app.state.database.connection() as db:job_id=db.execute("SELECT id FROM jobs WHERE task='source_ocr'").fetchone()[0]
                await client.post('/api/jobs/'+job_id+'/cancel',json={});await asyncio.wait_for(pending,2)
                job=(await client.get('/api/jobs/'+job_id)).json()
                batch=(await client.get('/api/ocr-batches/'+job['context']['ocr_batch_id'])).json()
                self.assertEqual(batch['completed_count'],0)
                self.assertNotIn('Late result',json.dumps(batch['results']))
                self.assertEqual((await client.get('/api/sources/'+source['id'])).json()['revision'],1)
        asyncio.run(scenario())

    def test_pass_deadline_keeps_completed_page_and_stops_without_an_auto_retry(self):
        source,_=self.source();self.app.state.source_ocr.pass_seconds=.25
        async def slow(path,kind,item,**options):
            self.calls.append(item['key'])
            if item['key']=='page:22':await asyncio.sleep(1)
            return reading('Completed '+item['key'])
        self.app.state.source_ocr.reader=slow
        batch,_,_=self.batch(source,['page:21','page:22'])
        self.assertEqual(batch['completed_count'],1)
        self.assertEqual(batch['results']['page:22']['code'],'NATIVE_TIMEOUT')
        self.assertEqual(self.calls,['page:21','page:22'])


class NativeProcessTests(unittest.IsolatedAsyncioTestCase):
    async def test_importing_app_does_not_open_or_migrate_the_real_database(self):
        command="from unittest.mock import patch\nwith patch('study_backend.db.Database',side_effect=AssertionError('import must not create a database')):\n import study_backend.app\nprint('import_only_ok')"
        result=await asyncio.to_thread(subprocess.run,[sys.executable,'-c',command],capture_output=True,text=True,
                                       env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1])},timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.strip(),'import_only_ok')

    async def test_cancel_terminates_native_child_instead_of_leaving_cpu_work_running(self):
        started=asyncio.Event()
        class Process:
            returncode=None;terminated=False
            async def communicate(self):started.set();await asyncio.Event().wait()
            def terminate(self):self.terminated=True;self.returncode=-15
            def kill(self):self.returncode=-9
            async def wait(self):return self.returncode
        process=Process()
        with patch('study_backend.native_ocr.binary',return_value=Path('/explicit-test-double')),patch('study_backend.native_ocr.asyncio.create_subprocess_exec',new=AsyncMock(return_value=process)):
            task=asyncio.create_task(run_native(['image-frames','fixture','21']))
            await asyncio.wait_for(started.wait(),2);task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
        self.assertTrue(process.terminated);self.assertIsNotNone(process.returncode)

    async def test_reader_checks_scope_and_retains_empty_detection_as_uncertain(self):
        packet={'kind':'frame','frame':21,'fragments':[],'engine':'explicit_native_reader_double','revision':1}
        value=decode_scope(json.dumps(packet).encode(),'frame',21);self.assertEqual(value['text'],'')
        packet['fragments']=[{'text':'wrong scope','locator':{'frame':22,'bounds':[.1,.1,.2,.2]}}]
        with self.assertRaises(ValueError):decode_scope(json.dumps(packet).encode(),'frame',21)
