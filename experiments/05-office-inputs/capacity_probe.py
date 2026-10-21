"""Native PDF boundary probe using generated pages, no external AI."""
from io import BytesIO
import json
from pathlib import Path
import sys
import time
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'backend'))
from study_backend.extract import extract
from study_backend.ocr import recognize,render_page

def main():
    writer=PdfWriter()
    for number in range(1,1002):
        page=writer.add_blank_page(width=300,height=200)
        stream=DecodedStreamObject();stream.set_data(f'BT /F1 18 Tf 20 100 Td (Capacity page {number}) Tj ET'.encode())
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
        page[NameObject('/Contents')]=writer._add_object(stream)
    out=BytesIO();writer.write(out);raw=out.getvalue()
    start=time.monotonic();fragments,warnings=extract('capacity-native.pdf',raw,ocr=False)
    assert len(fragments)==1000 and fragments[-1]['text']=='Capacity page 1000'
    assert fragments[-1]['locator']['page']==1000 and any('1000' in w for w in warnings)
    native_seconds=round(time.monotonic()-start,3)
    image,dimensions=render_page('capacity-native.pdf',raw,1000)
    Path('backend/runtime/capacity-page1000.png').write_bytes(image)
    ocr,notes=recognize('capacity-native.pdf',raw,pages=[1000])
    report={'purpose':'Generated one-line pages for native bounds verification; not a real book or quality benchmark', 'file_bytes':len(raw),'actual_pages':1001,'native_fragments':len(fragments),'native_read_seconds':native_seconds,'last_native_fragment':fragments[-1],'warnings':warnings,'rendered_page':1000,'render_dimensions':dimensions,'ocr_selected_page':1000,'ocr_text':[f['text'] for f in ocr],'ocr_warnings':notes,'external_ai_calls':0}
    Path('backend/evidence/source-capacity-native-boundary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print({k:report[k] for k in ['native_fragments','native_read_seconds','ocr_selected_page','ocr_text']})
if __name__=='__main__':main()
