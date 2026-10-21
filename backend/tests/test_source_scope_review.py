import copy,json,sqlite3,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from fastapi.testclient import TestClient
from study_backend.app import create_app
from study_backend.source_scope_review import review
from study_backend.source_collections import section_outline
from study_backend.source_context import fits
from study_backend.setup import PlanPreferences
from test_slice import TestProvider


def slides():
    texts=['Computer Networking: A Top-Down Approach, 8th edition, Pearson 2020','Chapter 6: The Link Layer',
           'A note on the use of these PowerPoint slides: they are freely available.',
           'If you use these slides, please mention their source.','COMPUTER NETWORKING Eighth Edition',
           'Link layer and LANs: our goals','understand principles behind link layer services: error detection and correction',
           'instantiation, implementation of link layer technologies']
    texts += ['Link layer services']+[f'Concept {i} is a definition with an example in the selected source.' for i in range(11)]
    return [{'id':f'r{i}','text':text,'locator':{'slide':1 if i<5 else 2 if i<8 else 3,'shape':i+1 if i<5 else i-4 if i<8 else i-7}} for i,text in enumerate(texts)]

def source(fragments):return {'id':'source-a','revision':2,'reviewed':True,'metadata':{'name':'Networking slides'},'fragments':fragments}

class ScopeReviewUnitTests(unittest.TestCase):
    def test_opening_suggestions_are_advisory_and_only_explicit_exclusion_moves_first_lesson(self):
        s=source(slides());original=copy.deepcopy(s);value=review(s);self.assertEqual(value['candidate_ids'],[f'r{i}' for i in range(8)])
        self.assertTrue(value['advisory_only']);self.assertFalse(value['automatic_changes']);self.assertFalse(value['ai_called']);self.assertEqual(s,original)
        prefs=PlanPreferences(source_id=s['id'],subject='Networks',goal='Learn the concepts',fragment_ids=[f['id'] for f in s['fragments']])
        full=section_outline(s,s['fragments'],prefs);self.assertEqual(full['units'][0]['source_refs'],[f'r{i}' for i in range(8)])
        kept=[f for f in s['fragments'] if f['id'] not in value['candidate_ids']];after=section_outline(s,kept,prefs)
        self.assertEqual(after['units'][0]['source_refs'],[f'r{i}' for i in range(8,20)])
        self.assertTrue(after['units'][0]['title'].startswith('Link layer services'))
        self.assertEqual(s,original)
    def test_copyright_as_the_subject_and_substantive_intro_text_are_not_blanket_excluded(self):
        fragments=[{'id':'theory','text':'Copyright is a legal right. For example, a creator may license reuse.','locator':{'slide':1}},
                   {'id':'goal','text':'Our goals','locator':{'slide':2}},
                   {'id':'definition','text':'A frame is a link-layer protocol data unit.','locator':{'slide':2}},
                   {'id':'later','text':'Learning objectives','locator':{'slide':20}}]
        self.assertEqual(review(source(fragments))['candidate_ids'],['goal'])
    def test_early_roadmap_is_suggested_but_later_roadmap_or_definitions_are_not_blanket_removed(self):
        fragments=[{'id':'heading','text':'Link layer, LANs: roadmap','locator':{'slide':3}},
                   {'id':'list','text':'introduction; error detection; Ethernet; switches','locator':{'slide':3}},
                   {'id':'definition','text':'An Ethernet frame is a link-layer data unit.','locator':{'slide':3}},
                   {'id':'later','text':'Roadmap','locator':{'slide':15}}]
        self.assertEqual(review(source(fragments))['candidate_ids'],['heading','list'])
    def test_collection_positions_do_not_mix_cover_classification_or_unit_references(self):
        a=slides()[:5];b=[{'id':'b1','text':'A frame is a unit of link layer data.','locator':{'slide':1,'component_source_id':'b'}}]
        for f in a:f['locator']['component_source_id']='a'
        value=review(source(a+b));self.assertNotIn('b1',value['candidate_ids'])
        p=PlanPreferences(source_id='source-a',subject='Networks',goal='Learn',fragment_ids=[f['id'] for f in a+b]);outline=section_outline(source(a+b),a+b,p)
        self.assertEqual(len(outline['units']),2);self.assertEqual(outline['units'][1]['source_refs'],['b1'])
    def test_oversized_slide_still_splits_with_no_lost_text_and_real_model_budget(self):
        fragments=[{'id':str(i),'text':'Long source definition. '*150,'locator':{'slide':3}} for i in range(13)]
        s=source(fragments);p=PlanPreferences(source_id=s['id'],subject='Long source',goal='Read all',fragment_ids=[f['id'] for f in fragments]);o=section_outline(s,fragments,p)
        self.assertGreater(len(o['units']),1);self.assertEqual([ref for u in o['units'] for ref in u['source_refs']],p.fragment_ids)
        by_id={f['id']:f for f in fragments}
        for u in o['units']:self.assertLessEqual(len(u['source_refs']),12);self.assertTrue(fits([by_id[r] for r in u['source_refs']]))

class ScopeReviewHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();r=Path(self.tmp.name);self.provider=TestProvider();self.app=create_app(r/'db.sqlite',r/'sources',self.provider,economy_enabled=False)
        self.client=TestClient(self.app,base_url='http://127.0.0.1');self.client.post('/api/session').raise_for_status()
        fragments=slides();s=self.client.post('/api/sources/text',json={'name':'Position fixtures','text':'\n'.join(f['text'] for f in fragments)}).json();self.sid=s['id']
        # Isolated extraction-position fixture: this does not test a PPTX parser.
        for f,position in zip(s['fragments'],fragments):f['locator']=position['locator']
        with self.app.state.database.connection(write=True) as db:db.execute('update extraction_revisions set content_json=? where source_id=? and revision=1',(json.dumps(s['fragments']),self.sid))
        response=self.client.post('/api/sources/'+self.sid+'/review',json={'expected_revision':1,'texts':[f['text'] for f in s['fragments']]});response.raise_for_status();self.s=response.json()
    def tearDown(self):self.client.close();self.tmp.cleanup()
    def get_review(self,revision=2):
        r=self.client.get('/api/sources/'+self.sid+'/scope-review',params={'revision':revision});r.raise_for_status();return r.json()
    def prefs(self,ids,excluded=None):return {'source_id':self.sid,'expected_extraction_revision':2,'subject':'Networks','goal':'Learn source concepts','fragment_ids':ids,'excluded_fragment_ids':excluded or []}
    def test_get_review_is_private_read_only_and_plan_scope_changes_only_after_explicit_choice(self):
        before=self.client.get('/api/sources/'+self.sid).json();report=self.get_review();self.assertEqual(len(report['candidate_ids']),8)
        self.assertEqual(self.client.get('/api/sources/'+self.sid).json(),before)
        all_ids=[f['id'] for f in self.s['fragments']]
        full=self.client.post('/api/plans/from-source-sections',json=self.prefs(all_ids));full.raise_for_status();self.assertEqual([r for u in full.json()['outline']['units'] for r in u['source_refs']],all_ids)
        selected=[r for r in all_ids if r not in report['candidate_ids']]
        explicit=self.client.post('/api/plans/from-source-sections',json=self.prefs(selected,report['candidate_ids']));explicit.raise_for_status();p=explicit.json()
        self.assertEqual(p['preferences']['excluded_fragment_ids'],report['candidate_ids']);self.assertEqual(p['outline']['units'][0]['source_refs'],selected)
        self.assertEqual(p['outline']['coverage']['not_selected_fragments'],8);self.assertEqual(self.provider.calls,0)
        with self.app.state.database.connection() as db:
            self.assertEqual(db.execute('select count(*) from jobs').fetchone()[0],0);self.assertEqual(db.execute('select count(*) from ai_usage').fetchone()[0],0)
    def test_old_review_stays_pinned_new_source_revision_stales_a_plan_request(self):
        before=self.get_review();texts=[f['text'].replace('our goals','a frame definition') for f in self.s['fragments']]
        self.client.post('/api/sources/'+self.sid+'/review',json={'expected_revision':2,'texts':texts}).raise_for_status()
        old=self.get_review();self.assertEqual(old['candidate_ids'],before['candidate_ids']);self.assertEqual(old['latest_revision'],3)
        stale=self.client.post('/api/plans/from-source-sections',json=self.prefs([f['id'] for f in self.s['fragments']]));self.assertEqual(stale.status_code,409)
    def test_other_owner_and_invalid_revision_cannot_read_the_report(self):
        with TestClient(self.app,base_url='http://127.0.0.1') as other:
            other.post('/api/session').raise_for_status();self.assertEqual(other.get('/api/sources/'+self.sid+'/scope-review?revision=2').status_code,404)
        self.assertEqual(self.client.get('/api/sources/'+self.sid+'/scope-review').status_code,422)
        self.assertEqual(self.client.get('/api/sources/'+self.sid+'/scope-review?revision=0').status_code,422)
    def test_excluded_unknown_or_overlapping_references_are_rejected(self):
        ids=[f['id'] for f in self.s['fragments']]
        for body in [self.prefs(ids,['foreign']),self.prefs(ids,[ids[0]])]:
            self.assertEqual(self.client.post('/api/plans/from-source-sections',json=body).status_code,422)
