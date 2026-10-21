"""Checkpointed, additive native OCR: preview first, never replace reviewed text."""
import asyncio
import copy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import time
import uuid
from datetime import datetime, timezone

from fastapi import BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import Field, StrictInt

from .models import Model
from .native_ocr import count_frames, read_scope
from .ocr import IMAGE_TYPES, render_page, binary
from .office_inputs import read_office, raster_asset
from .pdf_content import MAX_IMAGE_FRAMES, MAX_OCR_PAGES, MAX_PDF_PAGES
from .source_limits import MAX_TEXT, MAX_FRAGMENTS


def dump(value): return json.dumps(value, ensure_ascii=False)
def stamp(): return datetime.now(timezone.utc).isoformat()


class OCRStart(Model):
    expected_revision: StrictInt = Field(ge=0)
    items: list[str] = Field(default_factory=list, max_length=20)
    retry_no_text: bool = False


class OCRAction(Model):
    expected_revision: StrictInt = Field(ge=0)
    expected_batch_version: StrictInt = Field(ge=1)


def protected_fragment(fragment):
    locator=fragment['locator']
    return bool(fragment.get('edited_by_user') or locator.get('manual_math_correction') or
                locator.get('type') in {'vision_page','vision_office_image','user_transcription'} or
                fragment.get('provenance',{}).get('kind') in {'manual_transcription','ai_transcription'})


def same_anchor(left,right):
    if 'asset_id' in left:return left['asset_id']==right.get('asset_id')
    if left.get('slide') is not None:
        return left.get('slide')==right.get('slide') and left.get('shape')==right.get('shape')
    if left.get('table') is not None:
        return left.get('table')==right.get('table') and left.get('row')==right.get('row')
    return left.get('paragraph') is not None and left.get('paragraph')==right.get('paragraph')


def chunk_observations(result,start,end):
    """Keep only overlapping text, rather than copying a whole page into every chunk."""
    observations=result.get('observations',[])
    if '\n'.join(item.get('text','') for item in observations)!=result.get('text',''):
        return []  # Text/box alignment is unknown; the complete result stays in the batch.
    selected=[];offset=0
    for item in observations:
        finish=offset+len(item['text']);left=max(start,offset);right=min(end,finish)
        if left<right:
            selected.append({**item,'text':item['text'][left-offset:right-offset],
                             'source_text_range':[left,right],
                             'bounds_cover_full_observation':left!=offset or right!=finish})
        offset=finish+1
    return selected


class SourceOCR:
    def __init__(self,database,storage,jobs,source_snapshot,owned,reader=None,frame_counter=None):
        self.database,self.storage,self.jobs=database,storage,jobs
        self.source_snapshot,self.owned=source_snapshot,owned
        self.reader,self.frame_counter=reader or read_scope,frame_counter or count_frames
        self.pass_seconds=40

    async def inventory(self,source):
        if source['metadata'].get('kind')=='collection':
            raise HTTPException(422,'Đọc OCR trong từng tài liệu thành phần rồi tạo bộ nguồn mới; bản đang học được giữ.')
        name=source['metadata']['name'];suffix=Path(name).suffix.lower();path=self.storage/source['id']
        if suffix not in {'.pdf','.docx','.pptx'}|IMAGE_TYPES:
            raise HTTPException(422,'Nguồn này không có luồng OCR theo trang/hình.')
        try:raw=await asyncio.to_thread(path.read_bytes)
        except OSError as exc:raise HTTPException(422,'File gốc hiện không đọc được; chưa tạo lượt OCR hoặc đổi bản trích.') from exc
        if hashlib.sha256(raw).hexdigest()!=source['metadata']['sha256']:
            raise HTTPException(409,'File gốc không khớp bản đã lưu; chưa đọc hoặc ghép kết quả.')
        assets={};warnings=[]
        try:
            if suffix=='.pdf':
                from pypdf import PdfReader
                def page_count():
                    pdf=PdfReader(BytesIO(raw))
                    if pdf.is_encrypted:raise ValueError('PDF có mật khẩu.')
                    return len(pdf.pages)
                total=await asyncio.to_thread(page_count);kind='page'
                items=[{'key':f'page:{i}','index':i,'locator':{'type':'ocr_page','page':i,'page_index_base':1}}
                       for i in range(1,min(total,MAX_PDF_PAGES)+1)]
            elif suffix in IMAGE_TYPES:
                total=await self.frame_counter(path);kind='frame'
                items=[{'key':f'frame:{i}','index':i,'locator':{'type':'ocr_image','frame':i}}
                       for i in range(1,min(total,MAX_IMAGE_FRAMES)+1)]
            else:
                _,images,warnings=await asyncio.to_thread(read_office,name,raw);kind='asset';total=len(images)
                items=[{'key':'asset:'+asset.id,'asset_id':asset.id,'index':index,
                        'locator':asset.locator,'supported':asset.public()['raster_review_supported']}
                       for index,asset in enumerate(images,1)]
                assets={'asset:'+asset.id:asset for asset in images}
        except HTTPException:raise
        except Exception as exc:
            raise HTTPException(422,'Chưa liệt kê được trang/hình từ file gốc. Có thể đối chiếu và bổ sung bản chép tay.') from exc
        if total>len(items):warnings.append('Phần vượt 1.000 trang/khung hoặc inventory Office chưa thuộc lượt đọc này.')
        fragments=source['fragments'];attempts=source['metadata'].get('native_ocr_items',{})
        global_protection=any(protected_fragment(f) and
            not any(key in f['locator'] for key in ['page','frame','asset_id','paragraph','table','slide']) for f in fragments)
        for item in items:
            locator=item['locator']
            same=[f for f in fragments if (same_anchor(f['locator'],locator) if kind=='asset' else
                                          f['locator'].get(kind)==item['index'])]
            protected=global_protection or any(protected_fragment(f) for f in same)
            ocr=any(f.get('provenance',{}).get('kind') in {'native_ocr_batch','ocr_supplement','office_image_ocr'} or
                    f['locator'].get('type') in {'ocr_page','ocr_image'} or
                    f['locator'].get('extraction_method')=='ocr_supplement' for f in same)
            native=kind=='page' and any(f['locator'].get('type')=='page' and
                                       not f['locator'].get('visual_review',{}).get('raster_regions') and
                                       not f['locator'].get('visual_review',{}).get('analysis_incomplete') for f in same)
            state=('protected' if protected else 'unsupported' if item.get('supported') is False else
                   'text_available_unverified' if ocr else 'native_text' if native else
                   'no_text_detected' if attempts.get(item['key'],{}).get('state')=='no_text' else 'pending')
            item['state']=state
        return {'kind':kind,'items':items,'assets':assets,'total':total,'warnings':warnings,
                'global_protection':global_protection,'path':path}

    def snapshot(self,db,batch_id,owner):
        row=self.owned(db,'source_ocr_batches',batch_id,owner)
        items=json.loads(row.pop('items_json'));results=json.loads(row.pop('results_json'))
        job=db.execute("SELECT id,status FROM jobs WHERE task='source_ocr' AND json_extract(payload_json,'$.ocr_batch_id')=? ORDER BY created_at DESC,id DESC LIMIT 1",(batch_id,)).fetchone()
        complete=[key for key,result in results.items() if result['state'] in {'text','no_text'}]
        remaining=[item['key'] for item in items if item['key'] not in complete]
        status=row['state']
        if status=='draft':
            status=('reading' if job and job['status'] in {'queued','running'} else
                    'preview' if not remaining else 'partial' if complete else 'attention_required')
        source=self.source_snapshot(db,row['source_id'],owner)
        return {**{k:v for k,v in row.items() if k!='owner_id'},'status':status,'items':items,'results':results,
                'completed_count':len(complete),'remaining_count':len(remaining),'remaining_items':remaining,
                'no_text_count':sum(result['state']=='no_text' for result in results.values()),
                'job_id':job['id'] if job else None,'job_status':job['status'] if job else None,
                'source_revision':source['revision'],'stale':source['revision']!=row['base_revision'],
                'requires_review':True,'ai_calls':0,'coin_cost':0}

    def validate_action(self,db,batch_id,body,owner):
        batch=self.snapshot(db,batch_id,owner);source=self.source_snapshot(db,batch['source_id'],owner)
        if batch['state']!='draft' or batch['version']!=body.expected_batch_version:
            raise HTTPException(409,'Lượt đọc/bản xem trước đã đổi; tải lại trước khi thao tác.')
        if source['revision']!=body.expected_revision:
            raise HTTPException(409,'Bản trích đã đổi; tải lại trước khi thao tác.')
        if batch['job_status'] in {'queued','running'} or (batch['job_id'] in self.jobs.active and not self.jobs.active[batch['job_id']].done()):
            raise HTTPException(409,'Chờ trang đang đọc dừng hẳn trước khi dùng bản xem trước hoặc tiếp tục.')
        return batch,source

    def insert(self,db,batch_id,source,owner,kind,items,results=None,origin=None):
        db.execute('INSERT INTO source_ocr_batches VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (batch_id,owner,source['id'],source['revision'],source['metadata']['sha256'],kind,
                    dump(items),dump(results or {}),'draft',1,None,origin,stamp(),stamp()))

    async def work(self,batch_id,job_id,owner):
        with self.database.connection() as db:
            batch=self.snapshot(db,batch_id,owner);source=self.source_snapshot(db,batch['source_id'],owner)
        if source['revision']!=batch['base_revision']:
            raise HTTPException(409,'Nguồn đã đổi trước khi đọc; kết quả cũ vẫn được giữ.')
        inventory=await self.inventory(source);by_key={item['key']:item for item in inventory['items']}
        if self.reader is read_scope:await asyncio.to_thread(binary)
        results=batch['results'];deadline=time.monotonic()+self.pass_seconds;planned=len(batch['items'])
        reused=sum(result['state'] in {'text','no_text'} for result in results.values())
        with self.database.connection(write=True) as db:self.jobs.saved_stages(db,job_id,planned,reused,reused)
        for item in batch['items']:
            key=item['key'];old=results.get(key,{})
            if old.get('state') in {'text','no_text'} or old.get('attempts',0)>=2:continue
            if deadline-time.monotonic()<.1:break
            if key not in by_key or by_key[key]['state'] not in {'pending','no_text_detected'}:
                raise HTTPException(409,'Phạm vi đã có nội dung/bản sửa; chưa đọc đè. Tạo lại bản xem trước theo nguồn hiện tại.')
            attempts=old.get('attempts',0)+1
            results[key]={'state':'reading','attempts':attempts}
            with self.database.connection(write=True) as db:
                self.jobs.check(db,job_id)
                db.execute('UPDATE source_ocr_batches SET results_json=?,version=version+1,updated_at=? WHERE id=? AND state=\'draft\'',(dump(results),stamp(),batch_id))
            start=time.monotonic()
            try:
                remaining=max(.05,deadline-time.monotonic())
                value=await asyncio.wait_for(self.reader(inventory['path'],inventory['kind'],by_key[key],
                                                       assets=inventory['assets'],timeout_seconds=remaining),timeout=remaining)
                if not isinstance(value.get('text'),str) or len(value['text'])>120_000 or len(value.get('observations',[]))>2000:
                    raise ValueError('Kết quả OCR vượt giới hạn hoặc chưa hợp lệ.')
                used=sum(len(result.get('text','')) for result in results.values())
                if used+len(value['text'])>120_000:raise ValueError('Lượt đọc vượt 120.000 ký tự. Bổ sung phần đã xong rồi chọn lượt nhỏ hơn.')
                result={**value,'state':'text' if value['text'].strip() else 'no_text','attempts':attempts,
                        'elapsed_seconds':round(time.monotonic()-start,3)}
            except TimeoutError:
                result={'state':'error','attempts':attempts,'code':'NATIVE_TIMEOUT',
                        'message':'Phần này chưa hoàn tất trước hạn; giữ kết quả các phần trước.'}
            except ValueError as exc:
                result={'state':'error','attempts':attempts,'code':'NATIVE_READ_FAILED','message':str(exc)[:500]}
            results[key]=result
            done=sum(value['state'] in {'text','no_text'} for value in results.values())
            with self.database.connection(write=True) as db:
                self.jobs.check(db,job_id)
                row=db.execute('SELECT state FROM source_ocr_batches WHERE id=?',(batch_id,)).fetchone()
                if row['state']!='draft':raise HTTPException(409,'Lượt đọc đã đóng; không lưu kết quả về muộn.')
                db.execute('UPDATE source_ocr_batches SET results_json=?,version=version+1,updated_at=? WHERE id=?',(dump(results),stamp(),batch_id))
                db.execute('UPDATE jobs SET partial_json=? WHERE id=?',(dump({'ocr_batch_id':batch_id,'completed_items':done,'planned_items':planned}),job_id))
                self.jobs.saved_stages(db,job_id,planned,done,reused)
        with self.database.connection(write=True) as db:
            self.jobs.check(db,job_id)
            value={'ocr_batch_id':batch_id,'completed_items':sum(v['state'] in {'text','no_text'} for v in results.values()),'planned_items':planned}
            self.jobs.finish(db,job_id,value)
        return value

    def apply(self,db,batch,source,owner):
        if source['revision']!=batch['base_revision']:
            raise HTTPException(409,'Nguồn đã đổi trong lúc đọc. Giữ kết quả; tạo bản xem trước theo phiên bản mới thay vì đọc lại.')
        ready=[item for item in batch['items'] if batch['results'].get(item['key'],{}).get('state') in {'text','no_text'}]
        if not ready:raise HTTPException(422,'Chưa có phần hoàn tất để bổ sung; nguồn hiện tại không đổi.')
        fragments=copy.deepcopy(source['fragments']);added=[];progress=copy.deepcopy(source['metadata'].get('native_ocr_items',{}))
        for item in ready:
            result=batch['results'][item['key']]
            progress[item['key']]={'state':result['state'],'batch_id':batch['id'],'engine':result['engine'],'revision':result['revision']}
            text=result.get('text','').strip()
            for start in range(0,len(text),2400):
                part=text[start:start+2400]
                locator={**item['locator'],'extraction_method':'ocr_supplement','ocr_engine':result['engine'],
                         'ocr_revision':result['revision'],'character_start':start,'layout_unverified':True,
                         'ocr_observations':chunk_observations(result,start,start+len(part))}
                added.append({'text':part,'original_text':part,'locator':locator,'needs_review':True,
                              'provenance':{'kind':'native_ocr_batch','batch_id':batch['id'],'item_key':item['key'],
                                            'origin_batch_id':batch.get('origin_batch_id')}})
        fragments+=added
        if len(fragments)>MAX_FRAGMENTS or sum(len(f['text']) for f in fragments)>MAX_TEXT:
            raise HTTPException(422,'Nguồn đã chạm giới hạn lưu. Bản hiện tại và kết quả OCR được giữ; chia nguồn trước khi bổ sung.')
        kind=batch['kind'];field='office_order' if kind=='asset' else kind
        fragments.sort(key=lambda f:f['locator'].get(field,0))
        revision=source['revision']+1
        for index,fragment in enumerate(fragments):fragment['id']=f"{source['id']}:{revision}:{index}"
        metadata=source['metadata'];metadata['native_ocr_items']=progress
        metadata['last_native_ocr_batch']={'id':batch['id'],'items_added':len(ready),'no_text_detected':sum(batch['results'][i['key']]['state']=='no_text' for i in ready)}
        metadata['warnings']=list(dict.fromkeys(metadata['warnings']+['OCR bổ sung chưa xác minh công thức/bảng/sơ đồ. Không nhận ra chữ không có nghĩa trang trống; đối chiếu bản gốc.']))
        db.execute('INSERT INTO extraction_revisions VALUES (?,?,?,?,?)',(source['id'],revision,dump(fragments),None,stamp()))
        db.execute("UPDATE sources SET metadata_json=?,status='needs_review' WHERE id=?",(dump(metadata),source['id']))
        db.execute("UPDATE source_ocr_batches SET state='applied',applied_revision=?,version=version+1,updated_at=? WHERE id=?",(revision,stamp(),batch['id']))
        return self.source_snapshot(db,source['id'],owner)


def register_source_ocr(app,database,storage,jobs,source_snapshot,owned,user,reader=None,frame_counter=None):
    service=SourceOCR(database,storage,jobs,source_snapshot,owned,reader,frame_counter)
    app.state.source_ocr=service

    async def current(source_id,owner):
        with database.connection() as db:source=source_snapshot(db,source_id,owner)
        return source,await service.inventory(source)

    @app.get('/api/sources/{source_id}/ocr-status')
    async def status(source_id:str,owner=Depends(user)):
        source,inventory=await current(source_id,owner)
        with database.connection() as db:
            rows=db.execute("SELECT id,base_revision FROM source_ocr_batches WHERE owner_id=? AND source_id=? AND state='draft' ORDER BY created_at DESC LIMIT 5",(owner,source_id)).fetchall()
            batches=[service.snapshot(db,row['id'],owner) for row in rows]
        counts={state:sum(item['state']==state for item in inventory['items']) for state in
                ['pending','protected','unsupported','text_available_unverified','native_text','no_text_detected']}
        return {'source_id':source_id,'revision':source['revision'],'kind':inventory['kind'],
                'total_items':inventory['total'],'inventoried_items':len(inventory['items']),
                'items':inventory['items'],'counts':counts,'warnings':inventory['warnings'],
                'global_manual_protection':inventory['global_protection'],'next_items':[item['key'] for item in inventory['items'] if item['state']=='pending'][:20],
                'open_batches':[{'id':b['id'],'status':b['status'],'stale':b['stale'],'completed_count':b['completed_count'],'version':b['version'],'job_id':b['job_id'],'job_status':b['job_status']} for b in batches],
                'max_items_per_pass':20,'native_seconds_per_pass':service.pass_seconds,
                'ai_calls':0,'coin_cost':0,'text_detection_is_not_accuracy_verification':True}

    @app.post('/api/sources/{source_id}/ocr-batches')
    async def start(source_id:str,body:OCRStart,background:BackgroundTasks,request:Request,owner=Depends(user)):
        identity=jobs.identity(request,'source_ocr',{'source_id':source_id,**body.model_dump()},owner)
        cached=jobs.cached(owner,identity)
        if cached:return cached
        source,inventory=await current(source_id,owner)
        if source['revision']!=body.expected_revision:raise HTTPException(409,'Bản trích đã đổi; tải lại trước khi đọc tiếp.')
        eligible={item['key']:item for item in inventory['items'] if item['state']=='pending' or (body.retry_no_text and item['state']=='no_text_detected')}
        keys=body.items or [item['key'] for item in inventory['items'] if item['state']=='pending'][:MAX_OCR_PAGES]
        if not keys or len(keys)!=len(set(keys)) or any(key not in eligible for key in keys):
            raise HTTPException(422,'Chọn tối đa20 phần chưa đọc; không chọn phần đã có bản đọc/sửa. Không nhận ra chữ chỉ thử lại khi bạn chọn rõ.')
        if len(source['fragments'])>=MAX_FRAGMENTS or sum(len(f['text']) for f in source['fragments'])>=MAX_TEXT:
            raise HTTPException(422,'Bản trích đã chạm giới hạn lưu; chia nguồn trước khi đọc tiếp.')
        items=[eligible[key] for key in keys];batch_id=uuid.uuid4().hex
        def prepare(db):
            if source_snapshot(db,source_id,owner)['revision']!=body.expected_revision:
                raise HTTPException(409,'Bản trích đã đổi trước khi tạo lượt đọc.')
            prior=db.execute("SELECT id FROM source_ocr_batches WHERE owner_id=? AND source_id=? AND base_revision=? AND state='draft' LIMIT 1",(owner,source_id,body.expected_revision)).fetchone()
            if prior:raise HTTPException(409,'Có lượt OCR chưa dùng hoặc bỏ. Mở tiến trình để tiếp tục/xem kết quả; chưa đọc lặp.')
            service.insert(db,batch_id,source,owner,inventory['kind'],items)
        async def work(job_id):return await service.work(batch_id,job_id,owner)
        return jobs.create(owner,'source_ocr',{'source_id':source_id,'expected_revision':body.expected_revision,'ocr_batch_id':batch_id},background,work,identity,prepare)

    @app.get('/api/ocr-batches/{batch_id}')
    def batch(batch_id:str,owner=Depends(user)):
        with database.connection() as db:return service.snapshot(db,batch_id,owner)

    @app.post('/api/ocr-batches/{batch_id}/resume')
    async def resume(batch_id:str,body:OCRAction,background:BackgroundTasks,request:Request,owner=Depends(user)):
        identity=jobs.identity(request,'source_ocr',{'resume_batch_id':batch_id,**body.model_dump()},owner)
        cached=jobs.cached(owner,identity)
        if cached:return cached
        with database.connection() as db:
            value,source=service.validate_action(db,batch_id,body,owner)
            if value['stale']:raise HTTPException(409,'Nguồn đã đổi. Tạo bản xem trước theo bản nguồn mới để giữ phần OCR đã xong.')
            pending=[item for item in value['items'] if value['results'].get(item['key'],{}).get('state') not in {'text','no_text'} and value['results'].get(item['key'],{}).get('attempts',0)<2]
            if not pending:raise HTTPException(422,'Không còn phần có thể tiếp tục trong lượt này. Mỗi phần lỗi thử tối đa2 lần; phần không nhận ra chữ cần đối chiếu/sửa tay.')
            if sum(len(r.get('text','')) for r in value['results'].values())>=120_000:
                raise HTTPException(422,'Lượt này đã đầy. Bổ sung phần đã xong rồi đọc lượt nhỏ hơn.')
        def prepare(db):service.validate_action(db,batch_id,body,owner)
        async def work(job_id):return await service.work(batch_id,job_id,owner)
        return jobs.create(owner,'source_ocr',{'source_id':source['id'],'expected_revision':body.expected_revision,'ocr_batch_id':batch_id},background,work,identity,prepare)

    @app.post('/api/ocr-batches/{batch_id}/apply')
    def apply(batch_id:str,body:OCRAction,owner=Depends(user)):
        with database.connection(write=True) as db:
            value=service.snapshot(db,batch_id,owner)
            if value['state']=='applied':return source_snapshot(db,value['source_id'],owner,value['applied_revision'])
            value,source=service.validate_action(db,batch_id,body,owner)
            return service.apply(db,value,source,owner)

    @app.post('/api/ocr-batches/{batch_id}/discard')
    def discard(batch_id:str,body:OCRAction,owner=Depends(user)):
        with database.connection(write=True) as db:
            value,_=service.validate_action(db,batch_id,body,owner)
            db.execute("UPDATE source_ocr_batches SET state='discarded',version=version+1,updated_at=? WHERE id=?",(stamp(),batch_id))
            return {'id':batch_id,'state':'discarded','original_and_extraction_unchanged':True}

    @app.post('/api/ocr-batches/{batch_id}/rebase-preview')
    async def rebase(batch_id:str,body:OCRAction,owner=Depends(user)):
        with database.connection() as db:value,source=service.validate_action(db,batch_id,body,owner)
        if not value['stale']:raise HTTPException(409,'Bản nguồn chưa đổi; dùng bản xem trước hiện tại.')
        inventory=await service.inventory(source)
        eligible={item['key']:item for item in inventory['items'] if item['state'] in {'pending','no_text_detected'}}
        items=[eligible[item['key']] for item in value['items'] if item['key'] in eligible]
        if not items:raise HTTPException(422,'Các phần đã có bản đọc/sửa; không còn phần được phép bổ sung từ lượt này.')
        keys={item['key'] for item in items};results={key:copy.deepcopy(result) for key,result in value['results'].items() if key in keys}
        identity=uuid.uuid4().hex
        with database.connection(write=True) as db:
            service.validate_action(db,batch_id,body,owner)
            service.insert(db,identity,source,owner,inventory['kind'],items,results,origin=batch_id)
            db.execute("UPDATE source_ocr_batches SET state='superseded',version=version+1,updated_at=? WHERE id=?",(stamp(),batch_id))
            return {**service.snapshot(db,identity,owner),'skipped_protected_or_existing_items':[item['key'] for item in value['items'] if item['key'] not in keys]}

    @app.get('/api/ocr-batches/{batch_id}/items/{key}/image')
    async def item_image(batch_id:str,key:str,owner=Depends(user)):
        with database.connection() as db:
            value=service.snapshot(db,batch_id,owner);source=source_snapshot(db,value['source_id'],owner)
        item=next((i for i in value['items'] if i['key']==key),None)
        if not item:raise HTTPException(404,'Phần này không nằm trong lượt đọc.')
        inventory=await service.inventory(source)
        try:
            if value['kind']=='asset':image,_=await asyncio.to_thread(raster_asset,inventory['assets'][key])
            else:image,_=await asyncio.to_thread(render_page,source['metadata']['name'],inventory['path'].read_bytes(),item['index'])
        except (ValueError,KeyError) as exc:raise HTTPException(422,'Chưa dựng được ảnh phần đã chọn; file gốc vẫn còn.') from exc
        return Response(image,media_type='image/png',headers={'Cache-Control':'no-store'})

    return service
