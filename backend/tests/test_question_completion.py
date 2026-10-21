"""Behavioral checks for scoped missing-question proposals; providers are doubles."""
import copy
import asyncio
import json
import httpx
from fastapi.testclient import TestClient

from test_slice import SliceFixture, TestProvider
from study_backend.gemini import ProviderError
from study_backend.models import QUESTION_DRAFTS
from study_backend.providers import Choice


class QuestionCompletionTests(SliceFixture):
    def test_only_duplicate_completion_keeps_original_revision_and_no_proposal(self):
        course=self.partial_course(('mcq',))
        before=copy.deepcopy(course['content'])
        existing_prompt=before['units'][0]['data']['questions'][0]['prompt']
        original=self.provider.generate;calls=self.provider.calls
        async def duplicate(schema,instruction,fragments):
            value=await original(schema,instruction,fragments)
            if schema is QUESTION_DRAFTS['mcq']:value['question']['prompt']=existing_prompt
            return value
        self.provider.generate=duplicate
        response=self.post(course,['mcq']);jid=response.json()['job_id']
        job=self.client.get('/api/jobs/'+jid).json()
        self.assertEqual(job['status'],'failed')
        self.assertEqual(self.provider.calls-calls,1)
        self.assertEqual(job['partial']['question_rejections']['mcq']['code'],'QUESTION_DUPLICATE')
        self.assertIsNone(job['partial']['questions']['mcq']['question'])
        current=self.client.get(f"/api/courses/{course['id']}/editor").json()
        self.assertEqual(current['revision'],2);self.assertEqual(current['content'],before)

    def partial_course(self, missing=('cloze',)):
        original = self.provider.generate
        async def decline(schema, instruction, fragments):
            if schema in {QUESTION_DRAFTS[k] for k in missing}:
                self.provider.calls += 1
                return {'question': None, 'reason': 'Deliberate test-adapter decline.'}
            return await original(schema, instruction, fragments)
        self.provider.generate = decline
        course = self.course()
        self.provider.generate = original
        return course

    def post(self, course, stages, **kwargs):
        return self.client.post(f"/api/courses/{course['id']}/question-completion",
            json={'expected_revision': course['revision'], 'unit_id': 'unit-1', 'stages': stages, **kwargs})

    def editor(self, course):
        return self.client.get(f"/api/courses/{course['id']}/editor").json()

    def test_preview_only_appends_preserves_old_attempt_reading_cards_source_and_provenance(self):
        course = self.partial_course(); base = f"/api/courses/{course['id']}"
        before = copy.deepcopy(course['content']['units'][0])
        session = self.client.post(base+'/sessions', json={'expected_revision':2,'unit_id':'unit-1'}).json()
        q = session['questions'][0]
        self.client.post(f"/api/sessions/{session['id']}/answers",json={'item_id':q['id'],'answer':'A'}).raise_for_status()
        old_session = self.client.get(f"/api/sessions/{session['id']}").json()
        calls=self.provider.calls
        info=self.client.get(base+'/question-completion?unit_id=unit-1').json()
        self.assertEqual([x['stage'] for x in info['missing']],['cloze'])
        self.assertFalse(info['ai_called']); self.assertEqual(self.provider.calls,calls)
        result=self.job(self.post(course,['cloze']))
        self.assertEqual(self.provider.calls-calls,1)
        self.assertEqual(self.editor(course),course)
        proposal=self.client.get('/api/proposals/'+result['proposal_id']).json()
        self.assertEqual(proposal['after']['questions'][:-1],before['data']['questions'])
        self.assertEqual(proposal['scope']['target'],'question_completion')
        self.client.post('/api/proposals/'+result['proposal_id']+'/apply',json={'expected_revision':2}).raise_for_status()
        current=self.editor(course); unit=current['content']['units'][0]
        self.assertEqual(current['revision'],3)
        self.assertEqual({k:v for k,v in unit['data'].items() if k!='questions'}, {k:v for k,v in before['data'].items() if k!='questions'})
        for key in ('source_refs','source_plan_id'):
            self.assertEqual(unit.get(key),before.get(key))
        self.assertEqual(unit['generation']['provider'],before['generation']['provider'])
        self.assertEqual(unit['generation']['stage_providers'],before['generation']['stage_providers'])
        self.assertTrue(unit['generation']['question_coverage']['complete'])
        self.assertEqual(self.client.get(f"/api/sessions/{session['id']}").json(),old_session)
        new=self.client.post(base+'/sessions',json={'expected_revision':3,'unit_id':'unit-1'}).json()
        self.assertEqual([x['id'] for x in new['questions'][:-1]], [x['id'] for x in session['questions']])
        self.assertEqual([x['question_revision_id'] for x in new['questions'][:-1]], [x['question_revision_id'] for x in session['questions']])

    def test_filled_or_unknown_duplicate_or_stale_slots_do_not_call_model(self):
        course=self.partial_course();calls=self.provider.calls
        for stages,status in [(['mcq'],409),(['cloze','cloze'],422),(['cloze:9'],409)]:
            self.assertEqual(self.post(course,stages).status_code,status)
        self.assertEqual(self.post({**course,'revision':1},['cloze']).status_code,409)
        self.assertEqual(self.provider.calls,calls)

    def test_model_selection_is_pinned_for_new_stage_without_relabelling_old_stages(self):
        course=self.partial_course();other=TestProvider()
        registry=self.app.state.jobs.provider_router
        registry.choices['other']=Choice('other','Other test adapter',other)
        self.client.put('/api/ai/selection',json={'model_id':'other','expected_revision':0}).raise_for_status()
        calls=self.provider.calls
        r=self.post(course,['cloze']);result=self.job(r)
        self.assertEqual(self.provider.calls,calls);self.assertEqual(other.calls,1)
        job=self.client.get('/api/jobs/'+r.json()['job_id']).json()
        self.assertEqual(job['provider']['model_choice_id'],'other')
        self.assertIn('missing-question',job['provider']['prompt_version'])
        self.client.put('/api/ai/selection',json={'model_id':'injected','expected_revision':1}).raise_for_status()
        self.client.post('/api/proposals/'+result['proposal_id']+'/apply',json={'expected_revision':2}).raise_for_status()
        generation=self.editor(course)['content']['units'][0]['generation']
        self.assertEqual(generation['provider']['model_choice_id'],'injected')
        self.assertEqual(generation['question_completion_history'][-1]['stage_providers']['cloze']['model_choice_id'],'other')

    def test_failure_then_resume_reuses_only_valid_selected_stage(self):
        course=self.partial_course(('cloze','matching'));original=self.provider.generate
        async def fail(schema,*args):
            if schema is QUESTION_DRAFTS['matching']:raise ProviderError('CONNECTION_FAILED','Fixture disconnected',True)
            return await original(schema,*args)
        self.provider.generate=fail
        r=self.post(course,['cloze','matching']);jid=r.json()['job_id']
        failed=self.client.get('/api/jobs/'+jid).json()
        self.assertEqual(failed['status'],'failed');self.assertEqual(list(failed['partial']['questions']),['cloze'])
        self.assertEqual(self.post(course,['matching'],resume_job_id=jid).status_code,409)
        self.provider.generate=original;calls=self.provider.calls
        result=self.job(self.post(course,['cloze','matching'],resume_job_id=jid))
        self.assertEqual(self.provider.calls-calls,1);self.assertEqual(result['added_count'],2)
        self.assertTrue(result['question_coverage']['complete'])
        self.assertEqual(self.client.get('/api/jobs/'+jid).json(),failed)
        self.assertEqual(self.editor(course),course)

    def test_all_declined_produces_no_preview_and_releases_coin(self):
        course=self.partial_course();self.app.state.economy.enabled=True
        async def decline(*args):return {'question':None,'reason':'Fixture has no supported candidate.'}
        self.provider.generate=decline
        body={'expected_revision':2,'unit_id':'unit-1','stages':['cloze']}
        path=f"/api/courses/{course['id']}/question-completion"
        quote=self.client.post(path,json=body).json()['detail']
        self.assertEqual(quote['amount'],self.app.state.economy.policy['prices']['correction'])
        r=self.client.post(path,json=body,headers={'Idempotency-Key':'decline','Coin-Quote-Id':quote['quote_id']})
        jid=r.json()['job_id'];job=self.client.get('/api/jobs/'+jid).json()
        self.assertEqual(job['status'],'failed');self.assertIsNone(job['result'])
        with self.app.state.database.connection() as db:
            self.assertEqual(db.execute('select count(*) from revision_proposals').fetchone()[0],0)
            self.assertEqual(db.execute('select status from ai_usage where job_id=?',(jid,)).fetchone()[0],'released')
        wallet=self.client.get('/api/wallet').json();self.assertEqual(wallet['held'],0);self.assertEqual(wallet['balance'],20)
        self.assertEqual(self.editor(course),course)

    def test_quote_model_mismatch_idempotency_and_single_charge(self):
        course=self.partial_course();self.app.state.economy.enabled=True;calls=self.provider.calls
        path=f"/api/courses/{course['id']}/question-completion";body={'expected_revision':2,'unit_id':'unit-1','stages':['cloze']}
        quote=self.client.post(path,json=body).json()['detail']
        self.assertEqual(self.provider.calls,calls)
        self.app.state.jobs.provider_router.choices['other']=Choice('other','Other',TestProvider())
        self.client.put('/api/ai/selection',json={'model_id':'other','expected_revision':0}).raise_for_status()
        headers={'Idempotency-Key':'completion-once','Coin-Quote-Id':quote['quote_id']}
        self.assertEqual(self.client.post(path,json=body,headers=headers).status_code,409)
        quote2=self.client.post(path,json=body).json()['detail'];headers['Coin-Quote-Id']=quote2['quote_id']
        r=self.client.post(path,json=body,headers=headers);result=self.job(r)
        self.assertEqual(self.client.post(path,json=body,headers=headers).json(),r.json())
        self.client.post('/api/proposals/'+result['proposal_id']+'/discard').raise_for_status()
        self.assertEqual(self.client.get('/api/wallet').json()['balance'],18)
        self.assertEqual(self.editor(course),course)

    def test_source_without_sequence_is_blocked_without_job_or_quote(self):
        source=self.client.post('/api/sources/text',json={'name':'facts.txt','text':'IPv4 has 32 bits.'}).json()
        source=self.client.post(f"/api/sources/{source['id']}/review",json={'expected_revision':1,'texts':[f['text'] for f in source['fragments']]}).json()
        plan=self.job(self.client.post('/api/plans',json=self.preferences(source)))['plan_id']
        cid=self.client.post('/api/plans/'+plan+'/approve',json={'expected_revision':1}).json()['course_id']
        self.job(self.client.post(f'/api/courses/{cid}/generate',json={'expected_revision':1,'unit_id':'unit-1'}))
        course=self.client.get(f'/api/courses/{cid}/editor').json();calls=self.provider.calls
        self.app.state.economy.enabled=True
        missing=self.client.get(f'/api/courses/{cid}/question-completion?unit_id=unit-1').json()['missing']
        self.assertFalse(missing[0]['can_generate'])
        with self.app.state.database.connection() as db:count=db.execute('select count(*) from jobs').fetchone()[0]
        self.assertEqual(self.post(course,['ordering']).status_code,422);self.assertEqual(self.provider.calls,calls)
        with self.app.state.database.connection() as db:
            self.assertEqual(db.execute('select count(*) from jobs').fetchone()[0],count)
            self.assertEqual(db.execute('select count(*) from coin_quotes').fetchone()[0],0)

    def test_preview_does_not_overwrite_concurrent_course_revision(self):
        course=self.partial_course();result=self.job(self.post(course,['cloze']))
        card=copy.deepcopy(course['content']['units'][0]['data']['cards'][0]);card['back']='User edited card.'
        manual=self.client.post(f"/api/courses/{course['id']}/proposals",json={'expected_revision':2,'unit_id':'unit-1','target':'card','request':'Manual edit','replacement':card}).json()
        self.client.post('/api/proposals/'+manual['proposal_id']+'/apply',json={'expected_revision':2}).raise_for_status()
        self.assertEqual(self.client.post('/api/proposals/'+result['proposal_id']+'/apply',json={'expected_revision':2}).status_code,409)
        self.assertEqual(self.editor(course)['content']['units'][0]['data']['cards'][0]['back'],card['back'])
        self.assertEqual(self.client.get('/api/proposals/'+result['proposal_id']).json()['status'],'preview')

    def test_creator_exam_and_foreign_refs_guards(self):
        course=self.partial_course();path=f"/api/courses/{course['id']}/question-completion"
        other=TestClient(self.app,base_url='http://127.0.0.1');other.post('/api/session')
        self.assertEqual(other.get(path+'?unit_id=unit-1').status_code,404)
        self.assertEqual(other.post(path,json={'expected_revision':2,'unit_id':'unit-1','stages':['cloze']}).status_code,404)
        other.close();calls=self.provider.calls
        response=self.client.post(f"/api/courses/{course['id']}/sessions",json={'expected_revision':2,'unit_id':'unit-1','exercise':'test'})
        response.raise_for_status();session=response.json()
        self.assertEqual(self.post(course,['cloze']).status_code,403)
        self.assertEqual(self.provider.calls,calls)
        self.client.post('/api/sessions/'+session['id']+'/cancel').raise_for_status()
        original=self.provider.generate
        async def foreign(schema,*args):
            result=await original(schema,*args);result['question']['source_refs']=['foreign-source'];return result
        self.provider.generate=foreign
        r=self.post(course,['cloze']);job=self.client.get('/api/jobs/'+r.json()['job_id']).json()
        self.assertEqual(job['status'],'failed');self.assertEqual(job['error']['code'],'SOURCE_REFERENCE_MISMATCH')
        self.assertEqual(job['error']['invalid_ref_count'],1);self.assertNotIn('foreign-source',str(job['error']))
        self.assertEqual(self.editor(course),course)

    def test_manual_edits_reconcile_actual_counts_instead_of_stale_coverage(self):
        course=self.course();lesson=copy.deepcopy(course['content']['units'][0]['data'])
        lesson['questions']=[q for q in lesson['questions'] if q['kind']!='cloze']
        proposal=self.client.post(f"/api/courses/{course['id']}/proposals",json={'expected_revision':2,'unit_id':'unit-1','target':'lesson','request':'Remove a question','replacement':lesson}).json()
        self.client.post('/api/proposals/'+proposal['proposal_id']+'/apply',json={'expected_revision':2}).raise_for_status()
        info=self.client.get(f"/api/courses/{course['id']}/question-completion?unit_id=unit-1").json()
        self.assertEqual(info['existing_count'],4);self.assertEqual([x['stage'] for x in info['missing']],['cloze'])

    def test_active_room_blocks_completion_and_its_preview_but_preserves_it_for_later(self):
        course=self.partial_course();result=self.job(self.post(course,['cloze']))
        room=self.client.post('/api/rooms',json={'course_id':course['id'],'expected_revision':2,
            'unit_ids':['unit-1'],'question_count':1,'seconds_per_question':30,'nickname':'Host'},
            headers={'Idempotency-Key':'completion-room'})
        room.raise_for_status();rid=room.json()['room_id'];base='/api/rooms/'+rid
        peer=TestClient(self.app,base_url='http://127.0.0.1');self.addCleanup(peer.close)
        peer.post('/api/session').raise_for_status()
        peer.post('/api/rooms/join',json={'code':room.json()['join_code'],'nickname':'Peer'}).raise_for_status()
        state=self.client.get(base).json()
        self.client.post(base+'/start',json={'expected_event_index':state['event_index']},
            headers={'Idempotency-Key':'completion-room-start'}).raise_for_status()
        calls=self.provider.calls
        self.assertEqual(self.client.get(f"/api/courses/{course['id']}/question-completion?unit_id=unit-1").status_code,403)
        self.assertEqual(self.post(course,['cloze']).status_code,403)
        proposal='/api/proposals/'+result['proposal_id']
        self.assertEqual(self.client.get(proposal).status_code,403)
        self.assertEqual(self.client.post(proposal+'/apply',json={'expected_revision':2}).status_code,403)
        state=self.client.get(base).json()
        self.client.post(base+'/leave',json={'expected_event_index':state['event_index']},
            headers={'Idempotency-Key':'completion-room-leave'}).raise_for_status()
        self.assertEqual(self.client.get(proposal).json()['status'],'preview')
        self.client.post(proposal+'/apply',json={'expected_revision':2}).raise_for_status()
        self.assertEqual(self.provider.calls,calls)

    def test_cancel_after_first_checkpoint_keeps_partial_but_never_creates_preview(self):
        course=self.partial_course(('cloze','matching'));original=self.provider.generate
        async def scenario():
            started=asyncio.Event()
            async def wait(schema,*args):
                if schema is QUESTION_DRAFTS['matching']:
                    started.set();await asyncio.Future()
                return await original(schema,*args)
            self.provider.generate=wait
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://127.0.0.1',cookies=self.client.cookies) as client:
                request=asyncio.create_task(client.post(f"/api/courses/{course['id']}/question-completion",json={'expected_revision':2,'unit_id':'unit-1','stages':['cloze','matching']}))
                await asyncio.wait_for(started.wait(),2)
                with self.app.state.database.connection() as db:
                    jid=db.execute("select id from jobs where task='question_completion'").fetchone()[0]
                await client.post('/api/jobs/'+jid+'/cancel');await asyncio.wait_for(request,2)
                job=(await client.get('/api/jobs/'+jid)).json()
                self.assertEqual(job['status'],'cancelled');self.assertEqual(list(job['partial']['questions']),['cloze'])
                with self.app.state.database.connection() as db:
                    self.assertEqual(db.execute('select count(*) from revision_proposals').fetchone()[0],0)
            return jid
        jid=asyncio.run(scenario());self.assertEqual(self.editor(course),course)
        self.provider.generate=original;calls=self.provider.calls
        result=self.job(self.post(course,['cloze','matching'],resume_job_id=jid))
        self.assertEqual(result['added_count'],2);self.assertEqual(self.provider.calls-calls,1)

    def test_repeated_kind_slots_keep_remaining_identity_when_one_is_filled(self):
        # An actual source-backed three-cloze plan, with one initially valid
        # question and two intentional model declines.
        prefs=self.preferences
        self.preferences=lambda source:{**prefs(source),'question_types':['cloze'],'question_count':3}
        original=self.provider.generate;seen=0
        async def first_only(schema,*args):
            nonlocal seen
            if schema is QUESTION_DRAFTS['cloze']:
                seen+=1
                if seen>1:return {'question':None,'reason':'Fixture deferred.'}
            return await original(schema,*args)
        self.provider.generate=first_only;course=self.course()
        async def another(schema,*args):
            result=await original(schema,*args)
            result['question']['prompt']='Một câu mới ____'
            return result
        self.provider.generate=another
        result=self.job(self.post(course,['cloze:2']))
        self.assertEqual(result['question_coverage']['uncreated'][0]['stage'],'cloze:3')
        self.assertEqual(result['question_coverage']['generated_count'],2)
        self.assertFalse(result['question_coverage']['complete'])
