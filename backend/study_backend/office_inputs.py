"""Office source text/math and occurrence-scoped embedded images. No URL fetches."""
from dataclasses import dataclass
import hashlib
from io import BytesIO
import math
from pathlib import Path
import time
from zipfile import ZipFile, BadZipFile

from lxml import etree

from .office_math import M, transcribe

NS={'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
    'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'v':'urn:schemas-microsoft-com:vml'}
MAX_ASSETS=200


def local(node): return etree.QName(node).localname


def native_text(node, counter):
    equations=[]
    def walk(element):
        tag=local(element)
        if tag in {'del','moveFrom','instrText','delText','Fallback'}: return ''
        if element.tag=='{'+M+'}oMath':
            counter[0]+=1
            text,info=transcribe(element,counter[0]);equations.append(info)
            return text
        if tag in {'t'}: return element.text or ''
        if tag=='tab': return '\t'
        if tag in {'br','cr'}: return '\n'
        return ''.join(walk(x) for x in element if isinstance(x.tag,str))+('\n' if tag=='p' else '')
    return walk(node),equations


@dataclass
class Asset:
    id: str
    locator: dict
    blob: bytes | None
    suffix: str
    crop: tuple=(0,0,0,0)
    rotation: float=0
    flip_h: bool=False
    flip_v: bool=False
    warning: str=''

    def public(self):
        return {'id':self.id,'locator':self.locator,'bytes':len(self.blob or b''),
                'sha256':hashlib.sha256(self.blob).hexdigest() if self.blob is not None else None,
                'embedded':self.blob is not None,'raster_review_supported':self.blob is not None and self.suffix in {'.png','.jpg','.jpeg','.gif','.bmp','.tif','.tiff','.webp'},
                'crop':[x if math.isfinite(x) else None for x in self.crop],'rotation':self.rotation if math.isfinite(self.rotation) else None,'flip_h':self.flip_h,'flip_v':self.flip_v,'warning':self.warning}


def validate_package(data):
    try:
        with ZipFile(BytesIO(data)) as archive:
            items=archive.infolist()
            if len(items)>5000 or sum(x.file_size for x in items)>100*1024*1024:
                raise ValueError('File Office quá lớn sau giải nén.')
    except BadZipFile as exc: raise ValueError('File Word/PowerPoint không hợp lệ.') from exc


def read_office(filename,data):
    """Return native blocks and private image bytes, with stable original locations."""
    validate_package(data)
    blocks,assets,warnings=[],[],[];counter=[0];locations={};order=0;occurrence=0
    def add(node,locator):
        nonlocal order
        order+=1;locator={**locator,'office_order':order}
        if Path(filename).suffix.lower()=='.docx':locator['part']='word/document.xml'
        # Every paragraph in a cell shares the row locator, retaining an image's
        # exact cell/paragraph below instead of guessing a Word page number.
        locations[node]=locator
        for p in node.iter():
            if isinstance(p.tag,str) and local(p)=='p': locations.setdefault(p,locator)
        text,equations=native_text(node,counter)
        if equations:
            locator['office_math']=equations
            if any(not e['supported'] for e in equations): locator['unreadable_math']=True
            warnings.append('Office Math đã chép theo cấu trúc XML hỗ trợ; cần đối chiếu. Công thức chưa hỗ trợ được đánh dấu, không tự đoán.')
        if text.strip(): blocks.append({'text':text,'locator':locator,**({'needs_review':True} if equations else {})})

    def images(root,part,locator_default):
        nonlocal occurrence
        for node in root.iter():
            if not isinstance(node.tag,str) or node.tag not in {'{'+NS['a']+'}blip','{'+NS['v']+'}imagedata'}:continue
            if any(local(p)=='Fallback' for p in node.iterancestors()):continue
            occurrence+=1
            if len(assets)>=MAX_ASSETS:
                warnings.append('Chỉ liệt kê 200 lần xuất hiện hình đầu trong Office; hình còn lại chưa đọc.');break
            relation=node.get('{'+NS['r']+'}embed') or node.get('{'+NS['r']+'}id') or node.get('{'+NS['r']+'}link')
            if not relation:continue
            anchor=next((locations[p] for p in node.iterancestors() if p in locations),locator_default)
            locator={**{k:v for k,v in anchor.items() if k not in {'office_math','unreadable_math'}},'type':'office_image','part':str(part.partname).lstrip('/'),'image_occurrence':occurrence}
            identity=hashlib.sha256((locator['part']+'#'+str(occurrence)+'#'+relation).encode()).hexdigest()[:32]
            locator['asset_id']=identity
            blob=None;suffix='';warning=''
            try:
                rel=part.rels[relation]
                if rel.is_external:warning='Hình liên kết ngoài chưa tải; ứng dụng không tự truy cập địa chỉ trong file.'
                else:
                    target=rel.target_part;blob=target.blob;suffix=Path(str(target.partname)).suffix.lower()
            except (KeyError,ValueError,AttributeError):warning='Quan hệ hình bị thiếu hoặc chưa đọc được; giữ bản gốc để đối chiếu.'
            fill=node.getparent();crop_node=fill.find('a:srcRect',NS) if fill is not None else None
            try:crop=tuple(int(crop_node.get(k,'0'))/100000 for k in ['l','t','r','b']) if crop_node is not None else (0,0,0,0)
            except ValueError:crop=(float('nan'),0,0,0)
            container=next((p for p in node.iterancestors() if local(p) in {'pic','sp'}),None)
            transform=container.find('.//a:xfrm',NS) if container is not None else None
            try:rotation=int(transform.get('rot','0'))/60000 if transform is not None else 0
            except ValueError:rotation=float('nan')
            asset=Asset(identity,locator,blob,suffix,crop,rotation,
                        transform is not None and transform.get('flipH') in {'1','true'},transform is not None and transform.get('flipV') in {'1','true'},warning)
            assets.append(asset)
            if warning:warnings.append(warning)

    if Path(filename).suffix.lower()=='.docx':
        from docx import Document
        from docx.text.paragraph import Paragraph
        doc=Document(BytesIO(data));heading='';paragraph=table=0
        for block in doc.iter_inner_content():
            if isinstance(block,Paragraph):
                paragraph+=1
                if block.style and block.style.name.startswith('Heading'):heading=block.text
                add(block._p,{'type':'paragraph','paragraph':paragraph,'heading':heading})
            else:
                table+=1
                for row_index,row in enumerate(block.rows,1):
                    texts=[];equations=[];row_order=order+1
                    for col,cell in enumerate(row.cells,1):
                        order+=1
                        loc={'type':'table','table':table,'row':row_index,'cell':col,'heading':heading,'office_order':order}
                        locations.setdefault(cell._tc,loc)
                        for p_index,p in enumerate(cell.paragraphs,1):locations[p._p]={**loc,'paragraph_in_cell':p_index}
                        text,maths=native_text(cell._tc,counter);texts.append(text);equations.extend(maths)
                    loc={'type':'table','table':table,'row':row_index,'heading':heading,'office_order':row_order,'part':'word/document.xml'}
                    if equations:
                        loc.update(office_math=equations,unreadable_math=any(not e['supported'] for e in equations))
                    if any(t.strip() for t in texts):blocks.append({'text':' | '.join(t.strip() for t in texts),'locator':loc})
        images(doc.element.body,doc.part,{'office_order':order+1})
        if any('/header' in str(p.partname) or '/footer' in str(p.partname) or '/footnotes' in str(p.partname) for p in doc.part.package.parts):
            warnings.append('Header/footer/footnotes của Word chưa thuộc bản trích nội dung chính; đối chiếu bản gốc nếu cần học phần đó.')
    else:
        from pptx import Presentation
        deck=Presentation(BytesIO(data))
        for i,slide in enumerate(list(deck.slides)[:1000],1):
            def shapes(items,path=()):
                nonlocal order
                for j,shape in enumerate(items,1):
                    current=path+(j,);loc={'slide':i,'shape':j if not path else path[0],'shape_path':list(current),'shape_id':shape.shape_id,'part':str(slide.part.partname).lstrip('/')}
                    if hasattr(shape,'shapes'):shapes(shape.shapes,current);continue
                    if shape.has_text_frame:add(shape._element,{**loc,'type':'slide'})
                    elif shape.has_table:
                        for row_index,row in enumerate(shape.table.rows,1):
                            for col,cell in enumerate(row.cells,1):add(cell._tc,{**loc,'type':'slide_table','row':row_index,'cell':col})
                    else:order+=1
                    locations.setdefault(shape._element,{**loc,'office_order':order})
            shapes(slide.shapes)
            images(slide._element,slide.part,{'slide':i,'office_order':order+1})
        if len(deck.slides)>1000:warnings.append('Chỉ đọc 1000 slide đầu trong lượt này.')
        if any('/charts/' in str(p.partname) or '/diagrams/' in str(p.partname) or '/embeddings/' in str(p.partname) for p in deck.part.package.iter_parts()):
            warnings.append('Biểu đồ/SmartArt/OLE chưa được diễn giải như bảng dữ liệu; đối chiếu slide gốc, không tự suy dữ liệu từ hình.')
    if assets:warnings.append('Hình nhúng có vị trí riêng; bản OCR/AI cần đối chiếu. Hình trong nhóm được xem riêng, không phải ảnh render toàn trang/slide.')
    if any(f['locator'].get('office_math') for f in blocks):warnings.append('Office Math được chép theo cấu trúc hỗ trợ, cần đối chiếu; dạng chưa hỗ trợ không được tự đoán.')
    return blocks,assets,list(dict.fromkeys(warnings))


def raster_asset(asset):
    """Normalize only the displayed crop; never fetch linked or execute vector images."""
    from PIL import Image, ImageOps, UnidentifiedImageError
    if asset.blob is None:raise ValueError(asset.warning or 'Hình chưa có dữ liệu nhúng.')
    if not asset.public()['raster_review_supported']:raise ValueError('Định dạng hình này chưa có bộ raster an toàn; xem bản gốc hoặc chép tay.')
    if not all(math.isfinite(x) and 0<=x<1 for x in asset.crop) or not math.isfinite(asset.rotation):raise ValueError('Crop/rotation của hình chưa hỗ trợ; chưa gửi toàn ảnh thay cho phần hiển thị.')
    left,top,right,bottom=asset.crop
    if left+right>=1 or top+bottom>=1:raise ValueError('Khung crop không còn vùng ảnh hợp lệ.')
    try:
        with Image.open(BytesIO(asset.blob)) as original:
            if original.width*original.height>25_000_000:raise ValueError('Hình nhúng vượt 25 triệu pixel; cần chia nguồn.')
            image=ImageOps.exif_transpose(original);image=image.convert('RGBA')
            width,height=image.size
            image=image.crop((int(left*width),int(top*height),math.ceil((1-right)*width),math.ceil((1-bottom)*height)))
            if asset.flip_h:image=ImageOps.mirror(image)
            if asset.flip_v:image=ImageOps.flip(image)
            if asset.rotation%360:image=image.rotate(-asset.rotation,expand=True,resample=Image.Resampling.BICUBIC)
            background=Image.new('RGBA',image.size,'white');background.alpha_composite(image);image=background.convert('RGB');image.thumbnail((2400,2400))
            output=BytesIO();image.save(output,format='PNG');data=output.getvalue()
            if len(data)>8*1024*1024:raise ValueError('Ảnh đối chiếu vượt 8 MiB; cần chia nguồn.')
            return data,{'width':image.width,'height':image.height,'scope':'embedded_image_crop','locator':asset.locator,'crop':list(asset.crop),'rotation':asset.rotation}
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError) as exc:raise ValueError('Hình nhúng chưa giải mã được; bản gốc vẫn được giữ.') from exc


def read_with_ocr(filename,data,enabled,recognizer):
    blocks,assets,warnings=read_office(filename,data)
    deadline=time.monotonic()+40;processed=0
    for asset in assets:
        if not enabled or processed>=20 or time.monotonic()>=deadline:
            warnings.append('Một số hình nhúng chưa OCR; chọn hình để đọc lại hoặc bổ sung bản chép tay.');continue
        if not asset.public()['raster_review_supported']:
            if asset.blob is not None:warnings.append('Một hình nhúng chưa có bộ raster cho định dạng này; xem bản gốc hoặc chép tay.')
            continue
        processed+=1
        try:
            image,_=raster_asset(asset)
            fragments,notes=recognizer('office-asset.png',image,timeout_seconds=max(.05,min(40,deadline-time.monotonic())))
            observations=[{'text':f['text'],'bounds':f['locator'].get('bounds'),'recognizer_score':f.get('recognizer_score')} for f in fragments]
            text='\n'.join(f['text'] for f in fragments)
            blocks.append({'text':text,'locator':{**asset.locator,'ocr_observations':observations,'layout_unverified':True,'extraction_method':'ocr_supplement'},
                           'needs_review':True,'provenance':{'kind':'office_image_ocr','asset_id':asset.id,'image_sha256':hashlib.sha256(asset.blob).hexdigest()}})
            warnings.extend(notes)
        except ValueError as exc:warnings.append(f'Hình {asset.id[:8]} chưa đọc: {exc}')
    blocks.sort(key=lambda f:f['locator'].get('office_order',0))
    return blocks,list(dict.fromkeys(warnings))
