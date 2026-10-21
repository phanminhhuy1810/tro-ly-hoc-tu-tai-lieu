"""Source navigation/selection behaviour with real SQLite and no model calls."""
import base64
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from study_backend.app import create_app
from study_backend.db import Database
from test_slice import TestProvider


class SourceLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.root=Path(self.temp.name);self.provider=TestProvider()
        self.dbpath=self.root/'study.sqlite';self.storage=self.root/'sources'
        self.app=create_app(self.dbpath,self.storage,self.provider,economy_enabled=False)
        self.client=TestClient(self.app,base_url='http://127.0.0.1');self.client.post('/api/session').raise_for_status()

    def tearDown(self):self.client.close();self.temp.cleanup()

    def source(self,name='Mạng máy tính',text='IPv4 has32 bits.'):
        response=self.client.post('/api/sources/text',json={'name':name,'text':text});response.raise_for_status();return response.json()

    def review(self,source):
        response=self.client.post('/api/sources/'+source['id']+'/review',json={'expected_revision':source['revision'],'texts':[f['text'] for f in source['fragments']]})
        response.raise_for_status();return response.json()

    def get(self,path,params=None,client=None):
        response=(client or self.client).get(path,params=params);response.raise_for_status();return response.json()

    def test_library_and_legacy_walk_past100_without_skipping_ties_or_including_new_uploads(self):
        sources=[self.source(f'Network source {i:03d}',text='Private source body, never part of a library summary.') for i in range(115)]
        with self.app.state.database.connection(write=True) as db:db.execute("UPDATE sources SET created_at='2026-10-18T00:00:00+00:00'")
        first=self.get('/api/source-library');self.assertEqual(first['total'],115);self.assertEqual(len(first['items']),20)
        self.assertNotIn('Private source body',json.dumps(first));self.assertNotIn('fragments',first['items'][0])
        fresh=self.source('New after first page')
        ids=[s['id'] for s in first['items']];page=first
        for _ in range(20):
            if not page['next_cursor']:break
            page=self.get('/api/source-library',{'cursor':page['next_cursor']});ids.extend(item['id'] for item in page['items'])
        self.assertEqual(ids,[s['id'] for s in reversed(sources)])
        self.assertEqual(len(set(ids)),115);self.assertNotIn(fresh['id'],ids)
        back=self.get('/api/source-library',{'cursor':first['current_cursor']})
        self.assertEqual(back['items'],first['items'])
        self.assertEqual(self.get('/api/source-library')['items'][0]['id'],fresh['id'])
        response=self.client.get('/api/sources');response.raise_for_status();legacy=response.json()
        self.assertIsInstance(legacy,list);self.assertEqual(len(legacy),100)
        self.assertEqual(response.headers['x-source-total'],'116')
        rest=self.client.get('/api/sources',params={'cursor':response.headers['x-next-cursor']});rest.raise_for_status()
        self.assertEqual(len(rest.json()),16)
        self.assertEqual(len({s['id'] for s in legacy+rest.json()}),116)
        self.assertEqual(self.provider.calls,0)

    def test_name_search_is_accent_insensitive_literal_and_can_filter_review_state(self):
        a=self.review(self.source('Địa chỉ IPv4_100%'))
        b=self.source('Địa chỉ IPv6 draft')
        c=self.source('Mạng máy tính')
        result=self.get('/api/source-library',{'q':'DIA CHI ipv4'})
        self.assertEqual([s['id'] for s in result['items']],[a['id']])
        for query in ['%','_']:
            self.assertEqual([s['id'] for s in self.get('/api/source-library',{'q':query})['items']],[a['id']])
        self.assertEqual(self.get('/api/source-library',{'q':"' OR 1=1 --"})['items'],[])
        self.assertEqual([s['id'] for s in self.get('/api/source-library',{'reviewed':'true'})['items']],[a['id']])
        self.assertEqual({s['id'] for s in self.get('/api/source-library',{'reviewed':'false'})['items']},{b['id'],c['id']})

    def test_cursor_cannot_change_owner_query_limit_or_review_filter_or_echo_source_content(self):
        source=self.source('Owner-only title','Owner-only text');self.source('Second source')
        first=self.get('/api/source-library',{'limit':1});cursor=first['next_cursor']
        for params in [{'cursor':cursor},{'cursor':cursor,'limit':1,'q':'changed'},
                       {'cursor':cursor,'limit':1,'reviewed':'false'},{'cursor':'invalid!', 'limit':1},
                       {'cursor':'a'*2049,'limit':1},{'limit':101},{'limit':0}]:
            with self.subTest(params=params):self.assertEqual(self.client.get('/api/source-library',params=params).status_code,422)
        with TestClient(self.app,base_url='http://127.0.0.1') as other:
            other.post('/api/session').raise_for_status();self.assertEqual(self.get('/api/source-library',client=other)['items'],[])
            self.assertEqual(other.get('/api/source-library',params={'cursor':cursor,'limit':1}).status_code,422)
            self.assertEqual(other.get('/api/sources/'+source['id']+'/fragments',params={'revision':1}).status_code,404)
            self.assertEqual(other.get('/api/sources/'+source['id']+'/fragment-selection',params={'revision':1}).status_code,404)
        self.assertEqual(self.provider.calls,0)

    def test_an_owned_cursor_with_foreign_coordinates_does_not_grant_access(self):
        private=self.source('Private owner title','Private owner content')
        with TestClient(self.app,base_url='http://127.0.0.1') as other:
            other.post('/api/session').raise_for_status()
            response=other.post('/api/sources/text',json={'name':'Other owner','text':'Their source'});response.raise_for_status()
            page=self.get('/api/source-library',client=other);token=page['current_cursor']
            decoded=json.loads(base64.urlsafe_b64decode(token+'='*(-len(token)%4)))
            decoded['upper']=private['id']
            forged=base64.urlsafe_b64encode(json.dumps(decoded).encode()).decode().rstrip('=')
            response=other.get('/api/source-library',params={'cursor':forged})
            self.assertEqual(response.status_code,409)
            self.assertNotIn('Private owner',response.text)

    def test_backfill_restart_and_vacuum_keep_source_data_and_stable_pagination(self):
        sources=[self.source(f'Old source {i}') for i in range(8)]
        originals={s['id']:self.client.get('/api/sources/'+s['id']+'/original').content for s in sources}
        with self.app.state.database.connection(write=True) as db:
            db.execute('DROP TRIGGER source_library_created');db.execute('DROP TABLE source_library_entries')
            db.execute('DELETE FROM schema_versions WHERE version=16')
        # Simulate opening a schema15 database, without changing its originals
        # or extraction revisions, then opening it again without duplicate entries.
        Database(self.dbpath);Database(self.dbpath)
        first=self.get('/api/source-library',{'limit':3})
        with sqlite3.connect(self.dbpath) as db:
            before=db.execute('select sequence,source_id from source_library_entries order by sequence').fetchall()
            db.execute('VACUUM')
            after=db.execute('select sequence,source_id from source_library_entries order by sequence').fetchall()
            self.assertEqual(db.execute('select max(version) from schema_versions').fetchone()[0],18)
        self.assertEqual(before,after)
        ids=[i['id'] for i in first['items']];page=first
        while page['next_cursor']:
            page=self.get('/api/source-library',{'limit':3,'cursor':page['next_cursor']});ids.extend(i['id'] for i in page['items'])
        self.assertEqual(ids,[row[1] for row in reversed(after)])
        for source in sources:
            self.assertEqual(self.get('/api/sources/'+source['id'])['fragments'],source['fragments'])
            self.assertEqual(self.client.get('/api/sources/'+source['id']+'/original').content,originals[source['id']])

    def test_fragment_search_selection_and_source_section_plan_keep_the_exact_scope(self):
        text='\n'.join(f'Địa chỉ IPv4 mục {i}' if i%10==0 else f'Concept {i}: network facts' for i in range(180))
        source=self.review(self.source('Long source',text));base='/api/sources/'+source['id']
        first=self.get(base+'/fragments',{'revision':2,'q':'DIA CHI','limit':5})
        second=self.get(base+'/fragments',{'revision':2,'q':'dia chi','offset':5,'limit':5})
        self.assertEqual((first['total_fragments'],first['matched_fragments']),(180,18))
        self.assertFalse({f['id'] for f in first['items']} & {f['id'] for f in second['items']})
        selection=self.get(base+'/fragment-selection',{'revision':2,'q':'dia chi'})
        expected=[f['id'] for i,f in enumerate(source['fragments']) if i%10==0]
        self.assertEqual(selection['fragment_ids'],expected)
        self.assertEqual(self.get(base+'/fragment-selection',{'revision':2})['fragment_ids'],[f['id'] for f in source['fragments']])
        plan=self.client.post('/api/plans/from-source-sections',json={'source_id':source['id'],'expected_extraction_revision':2,
            'subject':'Mạng máy tính','goal':'Học phạm vi đã chọn','fragment_ids':selection['fragment_ids'],'language':'vi'})
        plan.raise_for_status();value=plan.json()
        assigned=[ref for unit in value['outline']['units'] for ref in unit['source_refs']]
        self.assertEqual(assigned,expected);self.assertEqual(len(assigned),len(set(assigned)))
        self.assertEqual(self.provider.calls,0)

    def test_search_stays_on_requested_revision_and_old_selection_cannot_create_a_new_stale_plan(self):
        source=self.review(self.source('Versions','Địa chỉ old value.\nOther source text.'));base='/api/sources/'+source['id']
        before=self.get(base+'/fragments',{'revision':2,'q':'old'});selection=self.get(base+'/fragment-selection',{'revision':2,'q':'old'})
        response=self.client.post(base+'/save-draft',json={'expected_revision':2,'texts':['Địa chỉ new value.','Other source text.']});response.raise_for_status()
        old=self.get(base+'/fragments',{'revision':2,'q':'old'});new=self.get(base+'/fragments',{'revision':3,'q':'new'})
        self.assertEqual(old['items'],before['items']);self.assertEqual(old['latest_revision'],3)
        self.assertEqual(new['matched_fragments'],1);self.assertFalse(new['reviewed'])
        stale=self.client.post('/api/plans/from-source-sections',json={'source_id':source['id'],'expected_extraction_revision':2,
            'subject':'Mạng máy tính','goal':'Old selection','fragment_ids':selection['fragment_ids'],'language':'vi'})
        self.assertEqual(stale.status_code,409)
        self.assertEqual(self.provider.calls,0)

    def test_matching_excerpt_snippet_shows_a_far_match_without_changing_the_original_text(self):
        text='x'*1900+' ĐỊA CHỈ needle '+('y'*300)
        source=self.source('Snippet',text);base='/api/sources/'+source['id']
        result=self.get(base+'/fragments',{'revision':1,'q':'dia chi needle'})
        self.assertEqual(result['matched_fragments'],1);item=result['items'][0]
        self.assertIn('needle',item['snippet']);self.assertLess(len(item['snippet']),400)
        self.assertEqual(item['text'],text)
        self.assertEqual(self.get(base)['fragments'],source['fragments'])
        self.assertEqual(self.get(base+'/fragments',{'revision':1,'q':'a synonym absent from source'})['matched_fragments'],0)

    def test_collection_search_uses_component_and_location_but_keeps_pinned_child_revision(self):
        a=self.source('MMT A','First A\nĐịa chỉ second A');b=self.source('MMT B','First B\nĐịa chỉ second B')
        response=self.client.post('/api/sources/collection',json={'name':'Combined','sources':[{'source_id':s['id'],'expected_revision':1} for s in [a,b]]})
        response.raise_for_status();source=response.json();base='/api/sources/'+source['id']
        result=self.get(base+'/fragment-selection',{'revision':1,'q':'dia chi','component_id':a['id'],'location_kind':'line','position':2})
        self.assertEqual(result['matched_fragments'],1)
        f=next(f for f in source['fragments'] if f['id']==result['fragment_ids'][0])
        self.assertEqual(f['locator']['component_source_id'],a['id'])
        self.assertEqual(f['locator']['component_revision'],1)
        self.assertEqual(self.get(base+'/fragments',{'revision':1,'position':2})['matched_fragments'],2)
        response=self.client.post('/api/sources/'+a['id']+'/save-draft',json={'expected_revision':1,'texts':['Changed','Changed']});response.raise_for_status()
        self.assertEqual(self.get(base+'/fragment-selection',{'revision':1,'q':'dia chi','component_id':a['id']})['fragment_ids'],result['fragment_ids'])

    def test_invalid_fragment_limits_filters_and_missing_revisions_are_rejected(self):
        source=self.source();base='/api/sources/'+source['id']
        for params in [{},{'revision':0},{'revision':1,'offset':-1},{'revision':1,'limit':101},
                       {'revision':1,'q':'x'*121},{'revision':1,'location_kind':'invented'},
                       {'revision':1,'position':0},{'revision':1,'component_id':'x'*129}]:
            with self.subTest(params=params):self.assertEqual(self.client.get(base+'/fragments',params=params).status_code,422)
        self.assertEqual(self.client.get(base+'/fragment-selection',params={'revision':99}).status_code,404)
        self.assertEqual(self.get(base)['fragments'],source['fragments'])
