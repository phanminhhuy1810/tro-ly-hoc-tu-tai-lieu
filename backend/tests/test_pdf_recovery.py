"""Real PDF structures, mocked OCR/provider; native quality is measured separately."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import subprocess
import sqlite3
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, DecodedStreamObject, NameObject, NumberObject

from study_backend.app import create_app
from study_backend.extract import extract
from study_backend.ocr import recognize, render_page, selected_result
from study_backend.pdf_content import visual_signals
from test_slice import TestProvider


def pdf_bytes(count=24, images=(24,), blank=(), vectors=()):
    writer=PdfWriter()
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    for i in range(1,count+1):
        page=writer.add_blank_page(720,540)
        resources=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
        content='' if i in blank else f'BT /F1 16 Tf 50 470 Td (Native text on page {i}) Tj ET\n'
        if i in images:
            image=DecodedStreamObject();image.set_data(b'\xff\xff\xff')
            image.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Image'),NameObject('/Width'):NumberObject(1),NameObject('/Height'):NumberObject(1),NameObject('/ColorSpace'):NameObject('/DeviceRGB'),NameObject('/BitsPerComponent'):NumberObject(8)})
            resources[NameObject('/XObject')]=DictionaryObject({NameObject('/Image'):writer._add_object(image)})
            content+='q 400 0 0 260 120 100 cm /Image Do Q\n'
        if i in vectors:content+='0 0 m\n'+'1 1 l\n'*40+'S\n'
        page[NameObject('/Resources')]=resources
        stream=DecodedStreamObject();stream.set_data(content.encode())
        page[NameObject('/Contents')]=writer._add_object(stream)
    output=BytesIO();writer.write(output);return output.getvalue()


class PDFRecovery(unittest.TestCase):
    def test_mixed_page_after_twenty_is_not_mistaken_for_complete_text(self):
        raw=pdf_bytes()
        native,warnings=extract('slides.pdf',raw,ocr=False)
        page=next(f for f in native if f['locator']['page']==24)
        self.assertIn('Native text',page['text'])
        self.assertTrue(page['locator']['visual_review']['raster_regions'])
        self.assertEqual(page['locator']['visual_review']['raster_ocr'],'not_read')
        self.assertTrue(any('Trang 24' in w and 'vùng ảnh' in w for w in warnings))
        with patch('study_backend.extract.recognize',return_value=([{'text':'OCR table: 11100000 | 224','locator':{'type':'ocr_page','page':24},'recognizer_score':.9}],[])) as ocr:
            improved,_=extract('slides.pdf',raw)
        self.assertEqual(ocr.call_args.kwargs['pages'],[24])
        self.assertEqual([f['text'] for f in improved if f['locator']['type']=='page'],[f['text'] for f in native])
        recovered=next(f for f in improved if f.get('provenance'))
        self.assertEqual(recovered['locator']['page'],24)
        self.assertTrue(recovered['needs_review']);self.assertTrue(recovered['locator']['layout_unverified'])
        self.assertEqual(recovered['provenance']['reason'],'mixed_page')

    def test_text_only_pdf_does_not_call_ocr_and_vector_relationships_are_flagged(self):
        with patch('study_backend.extract.recognize',side_effect=AssertionError('unnecessary OCR')):
            fragments,warnings=extract('notes.pdf',pdf_bytes(2,images=(),vectors=(2,)))
        self.assertEqual(len(fragments),2)
        self.assertGreaterEqual(fragments[1]['locator']['visual_review']['vector_paths'],30)
        self.assertTrue(any('Trang 2' in w and 'sơ đồ' in w for w in warnings))

    def test_ocr_failure_keeps_native_text_and_unread_image_warning(self):
        with patch('study_backend.extract.recognize',side_effect=ValueError('OCR unavailable')):
            fragments,warnings=extract('slides.pdf',pdf_bytes())
        self.assertEqual(len(fragments),24)
        self.assertIn('OCR unavailable',warnings)
        self.assertEqual(fragments[-1]['locator']['visual_review']['raster_ocr'],'not_read')

    def test_ocr_budget_prioritizes_blank_pages_without_reading_unselected_pages(self):
        with patch('study_backend.extract.recognize',return_value=([],[])) as ocr:
            _,warnings=extract('slides.pdf',pdf_bytes(25,images=tuple(range(1,25)),blank=(25,)))
        selected=ocr.call_args.kwargs['pages']
        self.assertEqual(len(selected),20);self.assertEqual(selected[0],25)
        self.assertTrue(any('một số vùng ảnh còn chưa đọc' in w for w in warnings))

    def test_selected_ocr_rejects_invalid_or_excessive_page_lists_before_execution(self):
        for pages in [[],[24,24],[1001],[True],[[1]],list(range(1,22))]:
            with self.subTest(pages=pages),patch('study_backend.ocr.binary',side_effect=AssertionError('should not execute')),self.assertRaises(ValueError):
                recognize('slides.pdf',b'fixture',pages=pages)
        with self.assertRaises(ValueError):recognize('image.png',b'fixture',pages=[1])
        with patch('study_backend.ocr.binary',side_effect=AssertionError('should not execute')),self.assertRaises(ValueError):render_page('slides.pdf',b'fixture',1001)

    def test_nested_form_image_placement_is_detected_without_decoding_pixels(self):
        reader=PdfReader(BytesIO(pdf_bytes(1,images=(1,))))
        page=reader.pages[0];original=page['/Contents'];resources=page['/Resources']
        form=DecodedStreamObject();form.set_data(original.get_object().get_data())
        form.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Form'),NameObject('/Resources'):resources})
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/XObject'):DictionaryObject({NameObject('/Form'):form})})
        stream=DecodedStreamObject();stream.set_data(b'q 1 0 0 1 0 0 cm /Form Do Q')
        page[NameObject('/Contents')]=stream
        signals=visual_signals(page)
        self.assertEqual(len(signals['raster_regions']),1)
        self.assertNotIn('analysis_incomplete',signals)

    def test_selected_native_ocr_keeps_late_page_geometry_and_marks_layout_unverified(self):
        observations=[{'text':t,'locator':{'type':'ocr_page','page':24,'page_index_base':1,'bounds':[.1,.2,.3,.04]},'recognizer_score':.9} for t in ['11100000','224']]
        reply={'fragments':observations,'warnings':['OCR requires review'],'engine':'explicit_test_double','revision':3}
        with patch('study_backend.ocr.binary',return_value=Path('/explicit-test-double')),patch('study_backend.ocr.subprocess.run',return_value=subprocess.CompletedProcess([],0,json.dumps(reply).encode())) as run:
            fragments,warnings=recognize('slides.pdf',b'explicit-test-original',pages=[24])
        self.assertEqual(run.call_args.args[0][1],'pdf-pages')
        self.assertEqual(run.call_args.args[0][-1],'24')
        self.assertEqual(len(fragments),1);self.assertEqual(fragments[0]['text'],'11100000\n224')
        self.assertEqual(fragments[0]['locator']['page'],24)
        self.assertEqual(fragments[0]['locator']['ocr_observations'][0]['bounds'],[.1,.2,.3,.04])
        self.assertTrue(fragments[0]['needs_review']);self.assertTrue(fragments[0]['locator']['layout_unverified'])

    def test_native_timeout_keeps_completed_pages_and_never_retries(self):
        packet={'kind':'page','page':24,'fragments':[{'text':'completed table cells','locator':{'type':'ocr_page','page':24,'bounds':[.1,.2,.3,.04]},'recognizer_score':.9}],'engine':'explicit_test_double','revision':3}
        output=json.dumps(packet).encode()+b'\n{"partial":"\xe1'
        with patch('study_backend.ocr.binary',return_value=Path('/explicit-test-double')),patch('study_backend.ocr.subprocess.run',side_effect=subprocess.TimeoutExpired([],40,output=output)) as run:
            fragments,warnings=recognize('slides.pdf',b'explicit-test-original',pages=[24,32])
        self.assertEqual(run.call_count,1)
        self.assertEqual(fragments[0]['locator']['page'],24)
        self.assertTrue(any('Trang 32 chưa hoàn tất' in w for w in warnings))
        self.assertTrue(any('không tự thử lại' in w for w in warnings))

    def test_native_page_stream_cannot_mix_unrequested_or_duplicate_pages(self):
        packet={'kind':'page','page':24,'fragments':[{'text':'cells','locator':{'page':24}}]}
        raw=json.dumps(packet).encode()+b'\n'
        with self.assertRaises(ValueError):selected_result(raw,[32])
        with self.assertRaises(ValueError):selected_result(raw+raw,[24])


class PDFReviewAPI(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();root=Path(self.tmp.name)
        class VisionProvider(TestProvider):
            async def transcribe_image(self,image):
                self.calls+=1
                return {'text':'Reviewed table: 11100000 | 224','uncertain_spans':[],'model':'explicit_test_double'}
        self.provider=VisionProvider();self.pages=[]
        def renderer(name,data,page):self.pages.append(page);return b'explicit_test_image',{'width':720,'height':540}
        self.app=create_app(root/'data.sqlite',root/'sources',self.provider,extractor=lambda name,data:extract(name,data,ocr=False),page_renderer=renderer,economy_enabled=False)
        self.client=TestClient(self.app,base_url='http://127.0.0.1');self.client.post('/api/session')
        self.raw=pdf_bytes(32,images=(24,),vectors=(32,))
        self.source=self.client.post('/api/sources/upload',files={'file':('slides.pdf',self.raw,'application/pdf')}).json()
        self.path='/api/sources/'+self.source['id']

    def tearDown(self):self.client.close();self.tmp.cleanup()

    def test_review_late_pdf_page_is_preview_scoped_private_and_revision_preserving(self):
        self.assertEqual(self.client.get(self.path+'/page-image?page=24').status_code,200)
        response=self.client.post(self.path+'/vision-review',json={'page':24,'expected_revision':1},headers={'Idempotency-Key':'late-page'})
        response.raise_for_status();job=self.client.get('/api/jobs/'+response.json()['job_id']).json()
        self.assertEqual(job['status'],'succeeded',job)
        proposal='/api/source-proposals/'+job['result']['source_proposal_id']
        preview=self.client.get(proposal).json();self.assertEqual(preview['page'],24)
        self.assertEqual(self.client.get(self.path).json()['fragments'],self.source['fragments'])
        foreign=TestClient(self.app,base_url='http://127.0.0.1');foreign.post('/api/session')
        self.assertEqual(foreign.get(self.path+'/page-image?page=24').status_code,404)
        self.assertEqual(foreign.post(proposal+'/apply',json={'expected_revision':1}).status_code,404);foreign.close()
        applied=self.client.post(proposal+'/apply',json={'expected_revision':1}).json()
        self.assertEqual(applied['revision'],2);self.assertFalse(applied['reviewed'])
        self.assertEqual(next(f['text'] for f in applied['fragments'] if f['locator']['page']==24),'Reviewed table: 11100000 | 224')
        self.assertEqual([f['text'] for f in applied['fragments'] if f['locator']['page']!=24],[f['text'] for f in self.source['fragments'] if f['locator']['page']!=24])
        self.assertEqual(self.client.get(self.path+'/original').content,self.raw)
        self.assertEqual(self.client.get(self.path+'?revision=1').json()['fragments'],self.source['fragments'])
        self.assertEqual(self.pages,[24,24])

    def test_page_bounds_are_validated_before_ai_and_images_reject_frames_after_thousand(self):
        for page in [0,1001]:
            self.assertEqual(self.client.get(self.path+f'/page-image?page={page}').status_code,422)
            self.assertEqual(self.client.post(self.path+'/vision-review',json={'page':page,'expected_revision':1}).status_code,422)
        self.assertEqual(self.provider.calls,0)

        self.assertEqual(self.client.get(self.path+'/page-image?page=32').status_code,200)
        self.assertEqual(self.pages,[32])
        failed=self.client.post('/api/sources/upload',files={'file':('image.png',b'explicit invalid image','image/png')})
        image_id=failed.json()['detail']['source_id']
        image_path='/api/sources/'+image_id
        self.assertEqual(self.client.get(image_path+'/page-image?page=1001').status_code,422)
        self.assertEqual(self.client.post(image_path+'/vision-review',json={'page':1001,'expected_revision':0}).status_code,422)
        self.assertEqual(self.provider.calls,0)

    def test_saved_legacy_vision_preview_still_applies_without_new_prompt_metadata(self):
        response=self.client.post(self.path+'/vision-review',json={'page':24,'expected_revision':1})
        response.raise_for_status();job=self.client.get('/api/jobs/'+response.json()['job_id']).json()
        identity=job['result']['source_proposal_id']
        with sqlite3.connect(Path(self.tmp.name)/'data.sqlite') as db:
            value=json.loads(db.execute('select content_json from source_proposals where id=?',(identity,)).fetchone()[0])
            value.pop('transcription_prompt_version',None)
            db.execute('update source_proposals set content_json=? where id=?',(json.dumps(value),identity))
        response=self.client.post('/api/source-proposals/'+identity+'/apply',json={'expected_revision':1})
        response.raise_for_status()
        recovered=next(f for f in response.json()['fragments'] if f['locator']['page']==24)
        self.assertEqual(recovered['provenance']['transcription_prompt_version'],'legacy_unrecorded')

    def test_labels_only_vision_cannot_silently_clear_diagram_review_signals(self):
        response=self.client.post(self.path+'/vision-review',json={'page':32,'expected_revision':1})
        response.raise_for_status();job=self.client.get('/api/jobs/'+response.json()['job_id']).json()
        path='/api/source-proposals/'+job['result']['source_proposal_id']
        proposal=self.client.get(path).json()
        self.assertTrue(proposal['layout_warnings'])
        self.assertIn('chưa mô tả rõ liên kết',proposal['warning'])
        # A saved proposal from before this guard gets the warning on read,
        # without asking the model to regenerate it.
        with sqlite3.connect(Path(self.tmp.name)/'data.sqlite') as db:
            row=db.execute('select content_json from source_proposals where id=?',(job['result']['source_proposal_id'],)).fetchone()
            value=json.loads(row[0]);value.pop('layout_warnings',None);value.pop('visual_review',None);value['warning']='Old proposal: requires source review.'
            db.execute('update source_proposals set content_json=? where id=?',(json.dumps(value),job['result']['source_proposal_id']))
        self.assertTrue(self.client.get(path).json()['layout_warnings']);self.assertEqual(self.provider.calls,1)
        response=self.client.post(path+'/apply',json={'expected_revision':1});response.raise_for_status()
        page=next(f for f in response.json()['fragments'] if f['locator']['page']==32)
        self.assertGreaterEqual(page['locator']['visual_review']['vector_paths'],30)
        self.assertTrue(page['locator']['layout_unverified']);self.assertFalse(response.json()['reviewed'])
