"""Long/multiple-source behavior; no real provider or remote service is used."""
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile, ZIP_STORED

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from study_backend.app import create_app
from study_backend.extract import extract
from study_backend.source_limits import MAX_TEXT
from study_backend.source_context import source_json
from test_slice import TestProvider
from test_office_inputs import word_fixture


class CapacityParsing(unittest.TestCase):
    def test_valid_office_larger_than_old_upload_cap_keeps_native_text(self):
        out=BytesIO()
        with ZipFile(BytesIO(word_fixture(images=False))) as original, ZipFile(out,'w',ZIP_STORED) as target:
            for entry in original.infolist():target.writestr(entry.filename,original.read(entry))
            target.writestr('developer-fixture-padding.bin',b'0'*(13*1024*1024))
        fragments,_=extract('large.docx',out.getvalue(),ocr=False)
        self.assertEqual([f['text'] for f in fragments],['Native paragraph before the image.','Native paragraph after the image.'])

    def test_long_paragraph_keeps_prefix_and_tail_beyond_old_text_cap(self):
        text='a'*150_000+' tail retained'
        fragments,warnings=extract('long.txt',text.encode(),ocr=False)
        self.assertEqual(''.join(f['text'] for f in fragments),text)
        self.assertFalse(warnings)
        fragments,warnings=extract('too-long.txt',b'x'*(MAX_TEXT+10),ocr=False)
        self.assertEqual(sum(len(f['text']) for f in fragments),MAX_TEXT)
        self.assertTrue(any('chưa được đọc' in w for w in warnings))
        self.assertEqual(fragments[-1]['locator']['character_start'],2400*(len(fragments)-1))

    def test_pdf_native_pages_after_200_are_read_with_exact_locations(self):
        writer=PdfWriter()
        for number in range(1,206):
            page=writer.add_blank_page(width=300,height=200)
            stream=DecodedStreamObject();stream.set_data(f'BT /F1 12 Tf 20 100 Td (Page {number}) Tj ET'.encode())
            font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
            page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
            page[NameObject('/Contents')]=writer._add_object(stream)
        out=BytesIO();writer.write(out)
        fragments,_=extract('long.pdf',out.getvalue(),ocr=False)
        self.assertEqual(len(fragments),205)
        self.assertEqual(fragments[-1]['text'],'Page 205')
        self.assertEqual(fragments[-1]['locator']['page'],205)


class CapacityAPI(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();root=Path(self.temp.name)
        self.provider=TestProvider()
        self.app=create_app(root/'data.sqlite',root/'sources',self.provider,extractor=lambda n,d:extract(n,d,ocr=False))
        self.client=TestClient(self.app,base_url='http://127.0.0.1');self.client.post('/api/session').raise_for_status()

    def tearDown(self):self.client.close();self.temp.cleanup()

    def source(self,name,count):
        response=self.client.post('/api/sources/text',json={'name':name,'text':'\n'.join(f'{name} excerpt {n}: IPv4 has 32 bits.' for n in range(count))})
        response.raise_for_status();return response.json()

    def collection(self,*sources):
        return self.client.post('/api/sources/collection',json={'name':'Network sources','sources':[{'source_id':s['id'],'expected_revision':s['revision']} for s in sources]})

    def review(self,source):
        response=self.client.post('/api/sources/'+source['id']+'/review',json={'expected_revision':source['revision'],'texts':[f['text'] for f in source['fragments']]})
        response.raise_for_status();return response.json()

    def test_collection_keeps_locations_pinned_revisions_originals_and_owner_access(self):
        a,b=self.source('Chapter A',22),self.source('Chapter B',17)
        response=self.collection(a,b);response.raise_for_status();combined=response.json()
        self.assertEqual(len(combined['fragments']),39);self.assertFalse(combined['reviewed'])
        self.assertEqual([f['text'] for f in combined['fragments']],[f['text'] for f in a['fragments']+b['fragments']])
        self.assertEqual(combined['fragments'][-1]['locator']['component_name'],'Chapter B.txt')
        self.assertEqual(combined['fragments'][-1]['locator']['line'],17)
        self.assertEqual(self.collection(a,b).json()['id'],combined['id'])
        originals=[self.client.get('/api/sources/'+s['id']+'/original').content for s in (a,b)]
        a['fragments'][0]['text']='Changed original extraction';a2=self.review(a)
        self.assertEqual(self.client.get('/api/sources/'+combined['id']).json()['fragments'],combined['fragments'])
        self.assertEqual(self.collection(a,b).status_code,409)
        new=self.collection(a2,b).json();self.assertNotEqual(new['id'],combined['id'])
        self.assertEqual([self.client.get('/api/sources/'+s['id']+'/original').content for s in (a,b)],originals)
        self.assertEqual(self.client.post('/api/sources/'+combined['id']+'/retry-extraction',json={'expected_revision':1}).status_code,422)
        with TestClient(self.app,base_url='http://127.0.0.1') as foreign:
            foreign.post('/api/session')
            self.assertEqual(foreign.get('/api/sources/'+combined['id']).status_code,404)
            self.assertEqual(foreign.get('/api/sources/'+a['id']+'/original').status_code,404)
            self.assertEqual(foreign.post('/api/sources/collection',json={'sources':[{'source_id':s['id'],'expected_revision':s['revision']} for s in (a2,b)]}).status_code,404)

    def test_all_80_excerpts_enter_free_roadmap_and_approval_does_not_generate(self):
        combined=self.collection(self.source('A',41),self.source('B',39)).json();source=self.review(combined)
        body={'source_id':source['id'],'expected_extraction_revision':source['revision'],'subject':'Networking','goal':'Learn both chapters','language':'en','fragment_ids':[f['id'] for f in source['fragments']],'question_types':['mcq'],'question_count':1}
        wallet_before=self.client.get('/api/wallet').json()
        response=self.client.post('/api/plans/from-source-sections',json=body);response.raise_for_status();plan=response.json()
        self.assertEqual(self.provider.calls,0)
        self.assertEqual(self.client.get('/api/wallet').json(),wallet_before)
        units=plan['outline']['units'];refs=[ref for u in units for ref in u['source_refs']]
        self.assertEqual(refs,body['fragment_ids']);self.assertTrue(all(len(u['source_refs'])<=8 for u in units))
        self.assertEqual(plan['outline']['coverage']['assigned_fragments'],80)
        self.assertEqual(plan['outline']['method'],'source_sections_not_ai')
        self.assertEqual(self.client.post('/api/plans',json=body).status_code,422)
        approved=self.client.post('/api/plans/'+plan['id']+'/approve',json={'expected_revision':1});approved.raise_for_status()
        course=self.client.get('/api/courses/'+approved.json()['course_id']).json()
        self.assertEqual(len(course['content']['units']),len(units))
        # Fixed answers still use the same engine; no generation occurs on approval.
        self.assertEqual(self.provider.calls,0)
        self.assertEqual(course['content']['units'][-1]['source_refs'],units[-1]['source_refs'])

    def test_long_paragraphs_are_partitioned_under_actual_provider_budget_without_text_loss(self):
        text='\n'.join(('IPv4 has 32 bits. '*130)+str(i) for i in range(20))
        response=self.client.post('/api/sources/text',json={'name':'Long source','text':text});response.raise_for_status()
        source=self.review(response.json());body={'source_id':source['id'],'subject':'Networking','goal':'Learn all','fragment_ids':[f['id'] for f in source['fragments']]}
        strategy=self.client.post('/api/plans/strategy',json=body);strategy.raise_for_status()
        self.assertEqual(strategy.json()['method'],'source_sections_not_ai')
        plan=self.client.post('/api/plans/from-source-sections',json=body).json()
        by_id={f['id']:{'id':f['id'],'text':f['text'],'locator':f['locator']} for f in source['fragments']}
        self.assertEqual([r for u in plan['outline']['units'] for r in u['source_refs']],body['fragment_ids'])
        self.assertTrue(all(len(source_json([by_id[r] for r in u['source_refs']]))<=9000 for u in plan['outline']['units']))
        self.assertGreater(len(plan['outline']['units']),1)
        self.assertEqual(self.provider.calls,0)

    def test_editing_long_roadmap_cannot_silently_drop_selected_tail_excerpts(self):
        source=self.review(self.source('Chapter',24))
        body={'source_id':source['id'],'subject':'Networking','goal':'Learn all','fragment_ids':[f['id'] for f in source['fragments']]}
        plan=self.client.post('/api/plans/from-source-sections',json=body).json()
        changed={'title':'Edited','units':plan['outline']['units'][:-1]}
        response=self.client.put('/api/plans/'+plan['id'],json={'expected_version':1,'outline':changed})
        self.assertEqual(response.status_code,422)
        self.assertEqual(len(self.client.get('/api/plans/'+plan['id']).json()['outline']['units']),3)
        self.assertEqual(self.provider.calls,0)

    def test_collection_rejects_duplicate_or_nested_inputs_and_stale_plan_scope(self):
        a,b=self.source('A',2),self.source('B',2)
        self.assertEqual(self.collection(a,a).status_code,422)
        combined=self.collection(a,b).json()
        self.assertEqual(self.collection(combined,a).status_code,422)
        source=self.review(combined)
        body={'source_id':source['id'],'expected_extraction_revision':1,'subject':'Networking','goal':'Learn','fragment_ids':[source['fragments'][0]['id']]}
        self.assertEqual(self.client.post('/api/plans/from-source-sections',json=body).status_code,409)
        body['expected_extraction_revision']=2;body['fragment_ids'].append('foreign:1:0')
        self.assertEqual(self.client.post('/api/plans/from-source-sections',json=body).status_code,422)

    def test_limits_endpoint_and_http_text_review_share_larger_budget(self):
        limits=self.client.get('/api/source-limits').json()
        self.assertEqual(limits['upload_bytes_per_file'],50*1024*1024)
        response=self.client.post('/api/sources/text',json={'name':'Long source','text':'a'*160_000+'TAIL'})
        response.raise_for_status();source=response.json();source=self.review(source)
        self.assertEqual(''.join(f['text'] for f in source['fragments']),'a'*160_000+'TAIL')
