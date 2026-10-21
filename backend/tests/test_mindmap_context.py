"""Mindmap help must select a node snapshot, not just a title in global chat."""
import copy
import json

from fastapi.testclient import TestClient
from test_slice import SliceFixture


class MindmapContextTests(SliceFixture):
    def setUp(self):
        super().setUp();self.value=self.course();self.base='/api/courses/'+self.value['id'];self.uid='unit-1'
        d=copy.deepcopy(self.value['content']['units'][0]['data']);refs=self.value['content']['units'][0]['source_refs']
        d['mindmap']=[{'title':'First idea','text':'FIRST_NODE_SNAPSHOT','source_refs':refs[:1]},
                      {'title':'Other idea','text':'UNRELATED_NODE_SNAPSHOT','source_refs':refs[-1:]}]
        self.value=self.edit(d);self.revision=self.value['revision']

    def edit(self,data):
        revision=self.value['revision']
        p=self.client.post(self.base+'/proposals',json={'unit_id':self.uid,'expected_revision':revision,'target':'lesson','index':0,
            'request':'Isolated fixture reading edit','replacement':data});p.raise_for_status()
        self.client.post('/api/proposals/'+p.json()['proposal_id']+'/apply',json={'expected_revision':revision}).raise_for_status()
        return self.client.get(self.base+'/editor').json()

    def open(self,index=0,revision=None,client=None):
        return (client or self.client).post(self.base+'/units/'+self.uid+'/mindmap/'+str(index)+'/help',
            json={'expected_revision':self.revision if revision is None else revision})

    def test_node_context_contains_only_its_text_refs_and_no_global_chat_or_other_node(self):
        calls=self.provider.calls;opened=self.open();opened.raise_for_status();tid=opened.json()['thread_id']
        self.assertFalse(opened.json()['ai_called']);safe=self.client.get('/api/help/threads/'+tid).json()
        node=self.value['content']['units'][0]['data']['mindmap'][0]
        self.assertEqual(safe['context']['kind'],'mindmap');self.assertEqual(safe['context']['node_index'],0)
        self.assertEqual(safe['context']['section'],node);self.assertEqual(safe['revision'],self.revision)
        self.assertEqual([f['id'] for f in safe['source_excerpts']],node['source_refs'])
        self.assertNotIn('UNRELATED_NODE_SNAPSHOT',json.dumps(safe));self.assertEqual(safe['messages'],[])
        self.assertEqual(self.client.get(self.base+'/chat').json(),[]);self.assertEqual(self.provider.calls,calls)
        self.assertEqual(self.open().json()['thread_id'],tid)

    def test_nodes_and_reading_sections_keep_separate_threads_drafts_and_cached_replies(self):
        first=self.open();first.raise_for_status();a=first.json()['thread_id'];b=self.open(1).json()['thread_id']
        section=self.client.post(self.base+'/units/'+self.uid+'/sections/0/help',json={'expected_revision':self.revision}).json()['thread_id']
        self.assertEqual(len({a,b,section}),3)
        self.client.put('/api/help/threads/'+a+'/draft',json={'text':'Ask about first idea','expected_version':0}).raise_for_status()
        self.assertEqual(self.client.get('/api/help/threads/'+b).json()['draft']['text'],'')
        self.assertEqual(self.client.get('/api/help/threads/'+section).json()['messages'],[])
        calls=self.provider.calls;self.job(self.client.post('/api/help/threads/'+a+'/actions',json={'action':'explain'}))
        self.assertEqual(self.provider.calls-calls,1)
        cached=self.client.post('/api/help/threads/'+a+'/actions',json={'action':'explain'}).json()
        self.assertTrue(cached['cached']);self.assertFalse(cached['ai_called']);self.assertEqual(self.provider.calls-calls,1)
        self.assertEqual(self.client.get('/api/help/threads/'+b).json()['messages'],[])

    def test_old_thread_keeps_node_snapshot_after_edit_and_new_open_rejects_stale_revision(self):
        opened=self.open();opened.raise_for_status();old=opened.json()['thread_id']
        before=self.client.get('/api/help/threads/'+old).json();data=copy.deepcopy(self.value['content']['units'][0]['data'])
        data['mindmap'][0]['text']='NEW_NODE_AFTER_EDIT';self.value=self.edit(data)
        self.assertEqual(self.open(revision=self.revision).status_code,409)
        current=self.open(revision=self.value['revision']);current.raise_for_status();self.assertNotEqual(current.json()['thread_id'],old)
        self.assertEqual(self.client.get('/api/help/threads/'+old).json(),before)
        self.job(self.client.post('/api/help/threads/'+old+'/actions',json={'action':'ask','message':'Explain this idea.'}))
        prompt=self.provider.instructions[-1];self.assertIn('FIRST_NODE_SNAPSHOT',prompt);self.assertNotIn('NEW_NODE_AFTER_EDIT',prompt)
        self.assertNotIn('UNRELATED_NODE_SNAPSHOT',prompt)

    def test_invalid_index_foreign_owner_stale_and_out_of_unit_ref_do_not_create_or_charge(self):
        calls=self.provider.calls;wallet=self.client.get('/api/wallet').json()
        peer=TestClient(self.app,base_url='http://127.0.0.1');peer.post('/api/session')
        with self.app.state.database.connection() as db:count=db.execute('SELECT count(*) FROM help_threads').fetchone()[0]
        for index in (-1,2,999):self.assertEqual(self.open(index).status_code,404)
        self.assertEqual(self.open(revision=1).status_code,409);self.assertEqual(self.open(client=peer).status_code,404);peer.close()
        # A malformed legacy node must not broaden its containing unit's scope.
        with self.app.state.database.connection(write=True) as db:
            row=db.execute('SELECT content_json FROM course_revisions WHERE course_id=? AND revision=?',(self.value['id'],self.revision)).fetchone()
            content=json.loads(row[0]);u=content['units'][0];u['source_refs']=u['source_refs'][:1]
            u['data']['mindmap'][0]['source_refs']=self.value['content']['units'][0]['source_refs'][-1:]
            db.execute('UPDATE course_revisions SET content_json=? WHERE course_id=? AND revision=?',(json.dumps(content),self.value['id'],self.revision))
        self.assertEqual(self.open().status_code,422)
        with self.app.state.database.connection() as db:self.assertEqual(db.execute('SELECT count(*) FROM help_threads').fetchone()[0],count)
        self.assertEqual(self.provider.calls,calls);self.assertEqual(self.client.get('/api/wallet').json(),wallet)

    def test_exam_blocks_new_open_read_and_actions_then_restores_saved_thread(self):
        opened=self.open();opened.raise_for_status();tid=opened.json()['thread_id'];before=self.client.get('/api/help/threads/'+tid).json()
        exam=self.client.post(self.base+'/sessions',json={'expected_revision':self.revision,'unit_id':self.uid,'exercise':'test'}).json()
        calls=self.provider.calls
        self.assertEqual(self.open().status_code,403);self.assertEqual(self.client.get('/api/help/threads/'+tid).status_code,403)
        self.assertEqual(self.client.post('/api/help/threads/'+tid+'/actions',json={'action':'ask','message':'Explain'}).status_code,403)
        self.assertEqual(self.provider.calls,calls)
        self.client.post('/api/sessions/'+exam['id']+'/cancel').raise_for_status()
        self.assertEqual(self.client.get('/api/help/threads/'+tid).json(),before)

    def test_note_uses_scoped_server_reply_and_keeps_original_course(self):
        opened=self.open();opened.raise_for_status();tid=opened.json()['thread_id'];before=copy.deepcopy(self.value)
        result=self.job(self.client.post('/api/help/threads/'+tid+'/actions',json={'action':'ask','message':'A note about this idea'}))
        note=self.client.post('/api/help/threads/'+tid+'/notebook',json={'message_id':result['message_id']});note.raise_for_status()
        self.assertIn('First idea',note.json()['body']);self.assertEqual(note.json()['label'],'ai')
        self.assertEqual(note.json()['source_refs'],self.value['content']['units'][0]['data']['mindmap'][0]['source_refs'])
        self.assertEqual(self.client.get(self.base+'/editor').json(),before)

    def test_zero_coin_and_removed_provider_do_not_block_context_or_successful_cache(self):
        opened=self.open();opened.raise_for_status();tid=opened.json()['thread_id']
        self.job(self.client.post('/api/help/threads/'+tid+'/actions',json={'action':'explain'}))
        self.app.state.economy.enabled=True;self.client.get('/api/wallet')
        with self.app.state.database.connection(write=True) as db:db.execute('UPDATE wallets SET balance=0')
        self.app.state.jobs.provider_router.choices.clear();calls=self.provider.calls
        self.open(1).raise_for_status();self.client.get('/api/help/threads/'+tid).raise_for_status()
        cached=self.client.post('/api/help/threads/'+tid+'/actions',json={'action':'explain'});cached.raise_for_status()
        self.assertTrue(cached.json()['cached']);self.assertFalse(cached.json()['ai_called'])
        self.assertEqual(self.provider.calls,calls);self.assertEqual(self.client.get('/api/wallet').json()['balance'],0)
