"""Resource deletion is reversible and cannot bypass history, Coin or sharing ACLs."""
import asyncio
import copy
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
import httpx

from study_backend.app import create_app
from study_backend.models import Outline
from test_slice import SliceFixture


class LifecycleTests(SliceFixture):
    def peer(self):
        c=TestClient(self.app,base_url='http://127.0.0.1');c.post('/api/session').raise_for_status()
        self.addCleanup(c.close);return c

    def inspect(self,kind,rid,client=None):
        response=(client or self.client).get(f'/api/{kind}s/{rid}/lifecycle');response.raise_for_status();return response.json()

    def change(self,kind,rid,restore=False,client=None,state=None):
        c=client or self.client;state=state or self.inspect(kind,rid,c)
        path=f'/api/{kind}s/{rid}'+('/restore' if restore else '')
        return c.request('POST' if restore else 'DELETE',path,json={'expected_revision':state['revision'],'expected_lifecycle_version':state['lifecycle_version']})

    def publish(self,course):
        response=self.client.post(f"/api/courses/{course['id']}/publication-preview",json={'expected_revision':course['revision'],'visibility':'public','share_original':True})
        response.raise_for_status();pid=response.json()['publication_id']
        self.client.post('/api/publications/'+pid+'/apply',json={'expected_revision':course['revision']}).raise_for_status()

    def test_source_trash_hides_every_read_and_reuse_route_restores_exact_original_after_restart(self):
        source=self.source();sid=source['id'];base='/api/sources/'+sid
        original=self.client.get(base+'/original').content;calls=self.provider.calls
        before=self.inspect('source',sid)
        self.change('source',sid,state=before).raise_for_status()
        self.assertEqual(self.client.get('/api/source-library').json()['items'],[])
        self.assertEqual(self.client.get('/api/sources').json(),[])
        for suffix in ['', '?revision=1', '/original','/scope-review?revision=1','/fragments?revision=1','/fragment-selection?revision=1']:
            self.assertEqual(self.client.get(base+suffix).status_code,404,suffix)
        self.assertEqual(self.client.post(base+'/review',json={'expected_revision':1,'texts':['Edited']}).status_code,404)
        self.assertEqual(self.client.post('/api/plans',json=self.preferences(source)).status_code,404)
        self.assertEqual(self.provider.calls,calls)
        self.assertEqual(self.client.get('/api/trash').json()['total'],1)
        restarted=create_app(self.app.state.database.path,Path(self.temp.name)/'sources',provider=self.provider,economy_enabled=False)
        with TestClient(restarted,base_url='http://127.0.0.1',cookies=self.client.cookies) as c:
            self.assertEqual(c.get('/api/trash').json()['total'],1)
            self.change('source',sid,True,c).raise_for_status()
            self.assertEqual(c.get(base).json(),source)
            self.assertEqual(c.get(base+'/original').content,original)
            self.assertEqual(c.get('/api/trash').json()['total'],0)

    def test_source_in_active_course_is_blocked_and_restore_requires_sources_first(self):
        course=self.course();cid=course['id'];source=self.client.get('/api/plans/'+course['plan_id']).json()['source_id']
        self.assertFalse(self.inspect('source',source)['can_delete'])
        refused=self.change('source',source)
        self.assertEqual(refused.status_code,409);self.assertEqual(refused.json()['detail']['code'],'RESOURCE_DEPENDENCIES')
        self.change('course',cid).raise_for_status();self.change('source',source).raise_for_status()
        self.assertEqual(self.change('course',cid,True).status_code,409)
        self.change('source',source,True).raise_for_status();self.change('course',cid,True).raise_for_status()
        self.assertEqual(self.client.get('/api/courses/'+cid+'/editor').json(),course)

    def test_old_course_revision_still_protects_its_source_after_all_future_units_change(self):
        sources=[]
        for _ in range(2):
            s=self.source();s=self.client.post('/api/sources/'+s['id']+'/review',json={'expected_revision':1,'texts':[f['text'] for f in s['fragments']]}).json();sources.append(s)
        pid=self.job(self.client.post('/api/plans',json=self.preferences(sources[0])))['plan_id']
        cid=self.client.post('/api/plans/'+pid+'/approve',json={'expected_revision':1}).json()['course_id']
        course=self.client.get('/api/courses/'+cid+'/editor').json();new=sources[1]
        edits=[{'unit_id':u['id'],'title':u['title'],'objective':u['objective'],'source_id':new['id'],
                'expected_extraction_revision':new['revision'],'source_refs':[f['id'] for f in new['fragments']]} for u in course['content']['units']]
        proposal=self.client.post('/api/courses/'+cid+'/future-plan-preview',json={'expected_revision':1,'units':edits,'request':'Replace every ungenerated unit source'})
        proposal.raise_for_status();self.client.post('/api/proposals/'+proposal.json()['proposal_id']+'/apply',json={'expected_revision':1}).raise_for_status()
        blockers=self.inspect('source',sources[0]['id'])['blockers']
        self.assertEqual([x['id'] for x in blockers],[cid])
        self.assertEqual(self.change('source',sources[0]['id']).status_code,409)

    def test_collection_dependency_restore_order_and_no_automatic_revival_on_recreate(self):
        sources=[self.source(),self.source()]
        body={'name':'Test collection','sources':[{'source_id':s['id'],'expected_revision':1} for s in sources]}
        collection=self.client.post('/api/sources/collection',json=body);collection.raise_for_status();collection=collection.json()
        self.assertEqual(self.change('source',sources[0]['id']).status_code,409)
        self.change('source',collection['id']).raise_for_status()
        another=self.client.post('/api/sources/collection',json=body);another.raise_for_status()
        self.assertNotEqual(another.json()['id'],collection['id'])
        self.change('source',another.json()['id']).raise_for_status();self.change('source',sources[0]['id']).raise_for_status()
        self.assertEqual(self.change('source',collection['id'],True).status_code,409)
        self.change('source',sources[0]['id'],True).raise_for_status();self.change('source',collection['id'],True).raise_for_status()

    def test_course_deletion_revokes_shares_but_keeps_private_results_notes_cards_and_old_keys(self):
        course=self.course();cid=course['id'];base='/api/courses/'+cid;peer=self.peer();outsider=self.peer()
        source=self.client.get('/api/plans/'+course['plan_id']).json()['source_id'];self.publish(course)
        peer.post(base+'/enroll').raise_for_status()
        self.assertEqual(peer.get('/api/sources/'+source+'/original').status_code,200)
        session=peer.post(base+'/sessions',json={'expected_revision':2,'unit_id':'unit-1'}).json()
        for item,question in zip(session['questions'],course['content']['units'][0]['data']['questions']):
            peer.post('/api/sessions/'+session['id']+'/answers',json={'item_id':item['id'],'answer':question['answer']}).raise_for_status()
        peer.post('/api/sessions/'+session['id']+'/complete').raise_for_status()
        old=peer.get('/api/sessions/'+session['id']).json()
        peer.post('/api/notebook',json={'body':'My own note','label':'user','source_refs':[]}).raise_for_status()
        peer.post('/api/cards/from-question',json={'session_id':session['id'],'item_id':session['questions'][0]['id']}).raise_for_status()
        notes=peer.get('/api/notebook').json();cards=[x for x in peer.get('/api/cards').json() if x['kind']=='personal']
        code=self.client.post(base+'/invite').json()['code']
        before=copy.deepcopy(course['content'])
        self.change('course',cid).raise_for_status()
        for c in [self.client,peer,outsider]:
            self.assertEqual(c.get(base).status_code,404);self.assertEqual(c.get(base+'/source-fragments').status_code,404)
            self.assertEqual(c.get('/api/community/'+cid).status_code,404)
            self.assertNotIn(cid,[x['id'] for x in c.get('/api/courses').json()])
        self.assertEqual(peer.get('/api/sources/'+source+'/original').status_code,404)
        self.assertEqual(peer.post(base+'/sessions',json={'expected_revision':2,'unit_id':'unit-1'}).status_code,404)
        self.assertEqual(peer.get('/api/sessions/'+session['id']).json(),old)
        self.assertEqual(len(peer.get(base+'/history').json()),1)
        self.assertEqual(outsider.get(base+'/history').status_code,404)
        self.assertEqual(peer.get('/api/notebook').json(),notes)
        self.assertEqual([x for x in peer.get('/api/cards').json() if x['kind']=='personal'],cards)
        self.assertEqual(peer.get('/api/trash').json()['total'],0)
        self.change('course',cid,True).raise_for_status()
        self.assertEqual(self.client.get(base+'/editor').json()['content'],before)
        self.assertEqual(peer.get(base).status_code,404)
        self.assertEqual(len(peer.get(base+'/history').json()),1)
        self.assertEqual(outsider.post('/api/community/join',json={'code':code}).status_code,404)
        self.assertNotIn(cid,[x['id'] for x in self.client.get('/api/community').json()])

    def test_open_sessions_drafts_and_room_are_cancelled_without_completion_reward(self):
        course=self.course();cid=course['id'];peer=self.peer();base='/api/courses/'+cid
        session=self.client.post(base+'/sessions',json={'expected_revision':2,'unit_id':'unit-1'}).json();item=session['questions'][0]
        self.client.put('/api/sessions/'+session['id']+'/draft',json={'item_id':item['id'],'answer':'B','expected_version':0}).raise_for_status()
        room=self.client.post('/api/rooms',json={'course_id':cid,'expected_revision':2,'unit_ids':['unit-1'],'question_count':1,'seconds_per_question':30,'nickname':'Host'},headers={'Idempotency-Key':'lifecycle-room'}).json()
        peer.post('/api/rooms/join',json={'code':room['join_code'],'nickname':'Peer'}).raise_for_status()
        room_path='/api/rooms/'+room['room_id'];state=self.client.get(room_path).json()
        self.client.post(room_path+'/start',json={'expected_event_index':state['event_index']},headers={'Idempotency-Key':'start-lifecycle'}).raise_for_status()
        effects=self.inspect('course',cid)['effects'];self.assertEqual(effects['sessions_to_cancel'],1);self.assertEqual(effects['rooms_to_cancel'],1)
        self.change('course',cid).raise_for_status()
        saved=self.client.get('/api/sessions/'+session['id']).json()
        self.assertEqual(saved['status'],'cancelled');self.assertEqual(saved['drafts'][item['id']]['answer'],'B');self.assertIsNone(saved['result'])
        self.assertEqual(peer.get(room_path).json()['phase'],'cancelled')
        self.assertEqual(self.client.post('/api/sessions/'+session['id']+'/complete').status_code,409)
        with self.app.state.database.connection() as db:
            self.assertEqual(db.execute('select count(*) from unit_completions').fetchone()[0],0)

    def test_lifecycle_version_prevents_old_delete_or_restore_and_replays_same_transition_once(self):
        source=self.source();sid=source['id'];active=self.inspect('source',sid)
        self.change('source',sid,state=active).raise_for_status()
        self.assertTrue(self.change('source',sid,state=active).json()['replayed'])
        trash=self.inspect('source',sid);self.change('source',sid,True,state=trash).raise_for_status()
        self.assertTrue(self.change('source',sid,True,state=trash).json()['replayed'])
        self.assertEqual(self.change('source',sid,state=active).status_code,409)
        self.change('source',sid).raise_for_status()
        self.assertEqual(self.change('source',sid,True,state=trash).status_code,409)
        with self.app.state.database.connection() as db:self.assertEqual(db.execute('select count(*) from resource_lifecycle_events').fetchone()[0],3)

    def test_simultaneous_delete_is_one_event_and_other_owners_cannot_read_or_restore(self):
        source=self.source();sid=source['id'];state=self.inspect('source',sid);peer=self.peer()
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda _:self.change('source',sid,state=state),range(2)))
        self.assertTrue(all(r.status_code==200 for r in results))
        self.assertEqual(sum(r.json()['replayed'] for r in results),1)
        self.assertEqual(peer.get('/api/sources/'+sid+'/lifecycle').status_code,404)
        self.assertEqual(self.change('source',sid,True,peer,state=self.inspect('source',sid)).status_code,404)
        self.assertEqual(peer.get('/api/trash').json()['total'],0)

    def test_restore_checks_original_integrity_and_keeps_tombstone_on_failure(self):
        source=self.source();sid=source['id'];self.change('source',sid).raise_for_status()
        (Path(self.temp.name)/'sources'/sid).write_bytes(b'Unexpected replacement')
        self.assertEqual(self.change('source',sid,True).status_code,409)
        self.assertIsNotNone(self.inspect('source',sid)['deleted_at'])

    def test_pre_delete_correction_and_publication_previews_cannot_apply_after_restore(self):
        course=self.course();cid=course['id'];base='/api/courses/'+cid
        card=copy.deepcopy(course['content']['units'][0]['data']['cards'][0]);card['back']='A pending change'
        proposal=self.client.post(base+'/proposals',json={'expected_revision':2,'unit_id':'unit-1','target':'card','request':'Manual proposal','replacement':card}).json()['proposal_id']
        publication=self.client.post(base+'/publication-preview',json={'expected_revision':2,'visibility':'public'}).json()['publication_id']
        self.change('course',cid).raise_for_status();self.assertEqual(self.client.get('/api/proposals/'+proposal).status_code,404)
        self.change('course',cid,True).raise_for_status()
        self.assertEqual(self.client.post('/api/proposals/'+proposal+'/apply',json={'expected_revision':2}).status_code,409)
        self.assertEqual(self.client.post('/api/publications/'+publication+'/apply',json={'expected_revision':2}).status_code,409)

    def test_deleting_during_paid_ai_releases_hold_and_blocks_late_commit(self):
        course=self.course();cid=course['id'];self.app.state.economy.enabled=True
        original=self.provider.generate
        async def scenario():
            started=asyncio.Event()
            async def late(*args):
                started.set()
                try:await asyncio.Future()
                except asyncio.CancelledError:return await original(*args)
            self.provider.generate=late
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://127.0.0.1',cookies=self.client.cookies) as c:
                path='/api/courses/'+cid+'/chat';body={'unit_id':'unit-1','message':'Explain this source'}
                quote=(await c.post(path,json=body)).json()['detail']
                request=asyncio.create_task(c.post(path,json=body,headers={'Idempotency-Key':'lifecycle-paid','Coin-Quote-Id':quote['quote_id']}))
                await asyncio.wait_for(started.wait(),2)
                self.assertEqual((await c.get('/api/wallet')).json()['held'],1)
                state=(await c.get('/api/courses/'+cid+'/lifecycle')).json();self.assertEqual(state['effects']['jobs_to_cancel'],1)
                response=await c.request('DELETE','/api/courses/'+cid,json={'expected_revision':2,'expected_lifecycle_version':0});response.raise_for_status()
                jid=(await asyncio.wait_for(request,2)).json()['job_id']
                job=(await c.get('/api/jobs/'+jid)).json();self.assertEqual(job['status'],'cancelled');self.assertIsNone(job['result'])
                self.assertEqual(job['error']['code'],'RESOURCE_DELETED')
                wallet=(await c.get('/api/wallet')).json();self.assertEqual((wallet['balance'],wallet['held']),(20,0))
                with self.app.state.database.connection() as db:self.assertEqual(db.execute("select count(*) from chat_messages where role='assistant'").fetchone()[0],0)
        asyncio.run(scenario())

    def test_deleting_source_cancels_pending_outline_without_orphaned_plan(self):
        source=self.source();source=self.client.post('/api/sources/'+source['id']+'/review',json={'expected_revision':1,'texts':[f['text'] for f in source['fragments']]}).json()
        async def scenario():
            started=asyncio.Event()
            async def block(schema,*args):
                self.assertIs(schema,Outline);started.set();await asyncio.Future()
            self.provider.generate=block
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://127.0.0.1',cookies=self.client.cookies) as c:
                pending=asyncio.create_task(c.post('/api/plans',json=self.preferences(source)))
                await asyncio.wait_for(started.wait(),2)
                response=await c.request('DELETE','/api/sources/'+source['id'],json={'expected_revision':2,'expected_lifecycle_version':0});response.raise_for_status()
                jid=(await asyncio.wait_for(pending,2)).json()['job_id'];self.assertEqual((await c.get('/api/jobs/'+jid)).json()['status'],'cancelled')
                with self.app.state.database.connection() as db:self.assertEqual(db.execute('select status from plans').fetchone()[0],'failed')
        asyncio.run(scenario())

    def test_coin_quote_from_before_delete_restore_cannot_start_a_new_job(self):
        course=self.course();cid=course['id'];self.app.state.economy.enabled=True
        path='/api/courses/'+cid+'/chat';body={'unit_id':'unit-1','message':'A source question'}
        quote=self.client.post(path,json=body).json()['detail'];calls=self.provider.calls
        self.change('course',cid).raise_for_status();self.change('course',cid,True).raise_for_status()
        response=self.client.post(path,json=body,headers={'Idempotency-Key':'old-lifecycle-quote','Coin-Quote-Id':quote['quote_id']})
        self.assertEqual(response.status_code,409);self.assertEqual(self.provider.calls,calls)
        fresh=self.client.post(path,json=body).json()['detail']
        self.assertNotEqual(fresh['quote_id'],quote['quote_id'])
        self.assertEqual(self.client.get('/api/wallet').json()['held'],0)

    def test_resource_change_after_request_snapshot_but_before_job_reservation_is_rejected(self):
        course=self.course();cid=course['id'];calls=self.provider.calls
        original=self.app.state.jobs.create;service=self.app.state.lifecycle
        from study_backend.lifecycle import LifecycleVersion
        owner=self.client.post('/api/session').json()['id']
        def race(*args,**kwargs):
            service.transition('course',cid,owner,LifecycleVersion(expected_revision=2,expected_lifecycle_version=0))
            service.transition('course',cid,owner,LifecycleVersion(expected_revision=2,expected_lifecycle_version=1),True)
            return original(*args,**kwargs)
        self.app.state.jobs.create=race
        result=self.client.post('/api/courses/'+cid+'/chat',json={'unit_id':'unit-1','message':'Before lifecycle changed'})
        self.assertEqual(result.status_code,409);self.assertEqual(self.provider.calls,calls)
        with self.app.state.database.connection() as db:self.assertEqual(db.execute("select count(*) from jobs where task='chat'").fetchone()[0],0)

    def test_trash_pagination_and_content_revision_checks(self):
        sources=[self.source() for _ in range(4)]
        for s in sources:self.change('source',s['id']).raise_for_status()
        first=self.client.get('/api/trash?kind=source&limit=3').json()
        second=self.client.get('/api/trash?kind=source&limit=3&offset=3').json()
        self.assertEqual(first['total'],4);self.assertTrue(first['has_more']);self.assertFalse(second['has_more'])
        self.assertEqual(len({s['id'] for s in first['items']+second['items']}),4)
        course=self.course();cid=course['id'];state=self.inspect('course',cid)
        card=copy.deepcopy(course['content']['units'][0]['data']['cards'][0]);card['back']='A newer revision'
        proposal=self.client.post('/api/courses/'+cid+'/proposals',json={'expected_revision':2,'unit_id':'unit-1','target':'card','request':'Update','replacement':card}).json()['proposal_id']
        self.client.post('/api/proposals/'+proposal+'/apply',json={'expected_revision':2}).raise_for_status()
        self.assertEqual(self.change('course',cid,state=state).status_code,409)
        self.assertIsNone(self.inspect('course',cid)['deleted_at'])

    def test_long_course_generation_instruction_never_contains_other_unit_or_plan_reference_ids(self):
        text='\n'.join('IPv4 has 32 bits. A /26 has 64 addresses. Note '+str(i) for i in range(24))
        source=self.client.post('/api/sources/text',json={'name':'long-scope.txt','text':text}).json()
        source=self.client.post('/api/sources/'+source['id']+'/review',json={'expected_revision':1,'texts':[f['text'] for f in source['fragments']]}).json()
        prefs={**self.preferences(source),'teacher_notes':'Keep the subnet term','terms_to_keep':['subnet'],'question_types':['mcq'],'question_count':1,'card_count':1}
        plan=self.client.post('/api/plans/from-source-sections',json=prefs).json()
        cid=self.client.post('/api/plans/'+plan['id']+'/approve',json={'expected_revision':1}).json()['course_id']
        before=self.client.get('/api/courses/'+cid+'/editor').json();unit=before['content']['units'][0]
        self.assertTrue(set(prefs['fragment_ids'])-set(unit['source_refs']))
        self.provider.instructions=[]
        self.job(self.client.post('/api/courses/'+cid+'/generate',json={'expected_revision':1,'unit_id':unit['id']}))
        for instruction in self.provider.instructions:
            for ref in set(prefs['fragment_ids'])-set(unit['source_refs']):self.assertNotIn(ref,instruction)
            self.assertNotIn(plan['id'],instruction);self.assertNotIn(source['id'],instruction)
            self.assertIn('Keep the subnet term',instruction);self.assertIn('subnet',instruction)
