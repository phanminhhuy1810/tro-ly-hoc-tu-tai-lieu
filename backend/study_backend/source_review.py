"""Bounded image rereading produces a preview; it never silently replaces OCR."""
import asyncio
import json
from pathlib import Path
import uuid
from datetime import datetime, timezone

from fastapi import BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import Field

from .extract import extract
from .source_limits import MAX_TEXT, MAX_FRAGMENTS
from .models import Model, VisionText
from .ocr import IMAGE_TYPES, render_page
from .pdf_content import MAX_PDF_PAGES, MAX_OCR_PAGES, MAX_IMAGE_FRAMES
from .office_inputs import read_office, raster_asset


class VisionRequest(Model):
    expected_revision: int = Field(ge=0)
    page: int = Field(default=1, ge=1, le=MAX_PDF_PAGES)
    asset_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')


class TranscriptionRequest(Model):
    expected_revision: int = Field(ge=0)
    text: str = Field(min_length=1,max_length=20_000)


def timestamp(): return datetime.now(timezone.utc).isoformat()
def dump(value): return json.dumps(value, ensure_ascii=False)


def layout_review(before, text):
    visual = next((f['locator']['visual_review'] for f in before if f['locator'].get('visual_review')), {})
    warnings = []
    if visual.get('vector_paths') and '->' not in text and '→' not in text and 'mô tả sơ đồ quan sát' not in text.casefold():
        warnings.append('Trang có nét vẽ/sơ đồ nhưng bản AI chưa mô tả rõ liên kết. Chép được nhãn chưa chứng minh đọc đúng mũi tên; giữ bản cũ hoặc bổ sung sau khi đối chiếu.')
    return visual, warnings


def register_source_review(app, database, storage, ai, jobs, source_snapshot, owned, user, renderer=None):
    renderer = renderer or render_page
    def snapshot(db, proposal_id, owner):
        row = owned(db, "source_proposals", proposal_id, owner)
        value = json.loads(row.pop("content_json"))
        visual, warnings = layout_review(value['before'], value['text'])
        value.setdefault('visual_review', visual)
        value['layout_warnings'] = list(dict.fromkeys(value.get('layout_warnings', []) + warnings))
        for warning in value['layout_warnings']:
            if warning not in value['warning']: value['warning'] += ' ' + warning
        return {**row, **value}

    def locate(source, page):
        suffix = Path(source["metadata"]["name"]).suffix.lower()
        if suffix != ".pdf" and suffix not in IMAGE_TYPES:
            raise HTTPException(422, "Chọn một trang PDF hoặc ảnh để đọc lại; nguồn chữ sửa trong bước duyệt.")
        if suffix != '.pdf' and page > MAX_IMAGE_FRAMES:
            raise HTTPException(422, 'Chọn khung ảnh trong phạm vi 1–1000.')
        return "page" if suffix == ".pdf" else "frame"

    def office_assets(source):
        if Path(source['metadata']['name']).suffix.lower() not in {'.docx','.pptx'}:
            raise HTTPException(422,'Chọn hình nhúng từ Word hoặc PowerPoint.')
        try:
            _,assets,warnings=read_office(source['metadata']['name'],(storage/source['id']).read_bytes())
        except Exception as exc:
            raise HTTPException(422,'Chưa đọc được danh sách hình trong file Office này; file gốc vẫn được giữ để sửa hoặc thay nguồn.') from exc
        return assets,warnings

    def office_asset(source,asset_id):
        assets,_=office_assets(source)
        asset=next((a for a in assets if a.id==asset_id),None)
        if asset is None:raise HTTPException(404,'Không có hình này trong nguồn gốc.')
        return asset

    @app.get('/api/sources/{source_id}/assets')
    async def list_assets(source_id:str,owner=Depends(user)):
        with database.connection() as db:source=source_snapshot(db,source_id,owner)
        assets,warnings=await asyncio.to_thread(office_assets,source)
        return {'source_id':source_id,'revision':source['revision'],'assets':[a.public() for a in assets],'warnings':warnings}

    @app.get('/api/sources/{source_id}/assets/{asset_id}/image')
    async def asset_image(source_id:str,asset_id:str,owner=Depends(user)):
        with database.connection() as db:source=source_snapshot(db,source_id,owner)
        try:
            asset=await asyncio.to_thread(office_asset,source,asset_id)
            image,_=await asyncio.to_thread(raster_asset,asset)
        except ValueError as exc:raise HTTPException(422,str(exc)) from exc
        return Response(image,media_type='image/png',headers={'Cache-Control':'no-store'})

    @app.get('/api/sources/{source_id}/page-image')
    async def page_image(source_id: str, page: int = 1, owner=Depends(user)):
        if not 1 <= page <= MAX_PDF_PAGES:
            raise HTTPException(422, "Chọn trang PDF trong phạm vi 1–1000 hoặc khung ảnh 1–1000.")
        with database.connection() as db:
            source = source_snapshot(db, source_id, owner)
            locate(source, page)
        try:
            image, _ = await asyncio.to_thread(renderer, source["metadata"]["name"], (storage/source_id).read_bytes(), page)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return Response(image, media_type='image/png')

    @app.post('/api/sources/{source_id}/vision-review')
    async def vision_review(source_id: str, body: VisionRequest, background: BackgroundTasks, request: Request, owner=Depends(user)):
        payload = {**body.model_dump(exclude_none=True), "source_id": source_id}
        identity = jobs.identity(request, "source_vision", payload, owner=owner)
        cached = jobs.cached(owner, identity)
        if cached:
            return cached
        with database.connection() as db:
            source = source_snapshot(db, source_id, owner)
            if source['revision'] != body.expected_revision:
                raise HTTPException(409, "Bản trích đã đổi; tải lại trước khi nhờ đọc ảnh.")
            kind = 'asset_id' if body.asset_id else locate(source, body.page)
        asset=None
        if body.asset_id:
            if body.page!=1:raise HTTPException(422,'Chọn hình nhúng bằng asset_id, không chọn thêm trang PDF.')
            asset=await asyncio.to_thread(office_asset,source,body.asset_id)
            if not asset.public()['raster_review_supported']:
                raise HTTPException(422,'Hình này chưa có bộ raster hoặc là liên kết ngoài. Dùng bản gốc/chép tay; chưa gọi AI.')
        if not hasattr(ai.choices[identity['_ai_model_id']].client, 'transcribe_image'):
            raise HTTPException(503, "Nguồn AI này chưa có bộ đọc ảnh; bản trích và sửa tay vẫn dùng được.")

        async def work(job_id):
            if asset is not None:image,dimensions=await asyncio.to_thread(raster_asset,asset)
            else:image, dimensions = await asyncio.to_thread(renderer, source['metadata']['name'], (storage/source_id).read_bytes(), body.page)
            reply = await ai.transcribe_image(image)
            value = VisionText.model_validate({k: reply[k] for k in ['text', 'uncertain_spans']}).model_dump()
            proposal_id = uuid.uuid4().hex
            scope_value=body.asset_id or body.page
            before = [f for f in source['fragments'] if f['locator'].get(kind) == scope_value]
            visual, layout_warnings = layout_review(before, value['text'])
            value.update(model=reply.get('model', 'configured_provider'), dimensions=dimensions,
                         transcription_prompt_version=reply.get('transcription_prompt_version', 'legacy_unrecorded'),
                         before=before, visual_review=visual, layout_warnings=layout_warnings,
                         requires_review=True, warning='AI có thể chép sai cả khi không báo phần chưa chắc. Chỉ dùng bản đã đối chiếu và xác nhận để tạo bài. ' + ' '.join(layout_warnings))
            if asset is not None:value.update(asset_id=asset.id,scope_locator=asset.locator)
            with database.connection(write=True) as db:
                jobs.check(db, job_id)
                db.execute('INSERT INTO source_proposals VALUES (?,?,?,?,?,?,?,?,?)', (proposal_id, owner, source_id, body.expected_revision, 0 if asset is not None else body.page, kind, dump(value), 'preview', timestamp()))
                result = {'source_proposal_id': proposal_id}
                jobs.finish(db, job_id, result)
            return result
        return jobs.create(owner, 'source_vision', payload, background, work, identity)

    @app.post('/api/sources/{source_id}/assets/{asset_id}/transcription-preview')
    async def manual_asset(source_id:str,asset_id:str,body:TranscriptionRequest,owner=Depends(user)):
        with database.connection() as db:
            source=source_snapshot(db,source_id,owner)
            if source['revision']!=body.expected_revision:raise HTTPException(409,'Bản trích đã đổi; tải lại trước khi sửa hình.')
        asset=await asyncio.to_thread(office_asset,source,asset_id)
        value={'text':body.text.strip(),'uncertain_spans':[],'model':'manual','manual_edit':True,
               'transcription_prompt_version':'manual','asset_id':asset_id,'scope_locator':asset.locator,
               'before':[f for f in source['fragments'] if f['locator'].get('asset_id')==asset_id],
               'requires_review':True,'warning':'Bản chép tay cho hình đã chọn, chưa áp dụng hoặc xác nhận chính xác.'}
        if not value['text']:raise HTTPException(422,'Nhập nội dung để xem trước.')
        identity=uuid.uuid4().hex
        with database.connection(write=True) as db:
            if source_snapshot(db,source_id,owner)['revision']!=body.expected_revision:raise HTTPException(409,'Bản trích đã đổi trong khi chuẩn bị xem trước.')
            db.execute('INSERT INTO source_proposals VALUES (?,?,?,?,?,?,?,?,?)',(identity,owner,source_id,body.expected_revision,0,'asset_id',dump(value),'preview',timestamp()))
            return snapshot(db,identity,owner)

    @app.post('/api/source-proposals/{proposal_id}/edit-preview')
    def edit_preview(proposal_id:str,body:TranscriptionRequest,owner=Depends(user)):
        with database.connection(write=True) as db:
            parent=snapshot(db,proposal_id,owner);source=source_snapshot(db,parent['source_id'],owner)
            if parent['status'] not in {'preview','discarded'} or source['revision']!=body.expected_revision or parent['base_revision']!=body.expected_revision:
                raise HTTPException(409,'Phạm vi/bản trích đã đổi; chưa ghi đè đề xuất cũ.')
            text=body.text.strip()
            if not text:raise HTTPException(422,'Nhập nội dung để xem trước.')
            value={k:v for k,v in parent.items() if k not in {'id','owner_id','source_id','base_revision','page','page_kind','status','created_at','layout_warnings','visual_review'}}
            value.update(text=text,model='manual',manual_edit=True,original_model=parent['model'],parent_proposal_id=proposal_id,
                         transcription_prompt_version='manual',uncertain_spans=[],warning='Bản sửa tay từ đề xuất đã lưu; đề xuất AI gốc vẫn giữ nguyên. Chưa áp dụng.')
            identity=uuid.uuid4().hex
            db.execute('INSERT INTO source_proposals VALUES (?,?,?,?,?,?,?,?,?)',(identity,owner,parent['source_id'],parent['base_revision'],parent['page'],parent['page_kind'],dump(value),'preview',timestamp()))
            return snapshot(db,identity,owner)

    @app.get('/api/source-proposals/{proposal_id}')
    def get_proposal(proposal_id: str, owner=Depends(user)):
        with database.connection() as db:
            return snapshot(db, proposal_id, owner)

    @app.post('/api/source-proposals/{proposal_id}/discard')
    def discard(proposal_id: str, owner=Depends(user)):
        with database.connection(write=True) as db:
            proposal = snapshot(db, proposal_id, owner)
            if proposal['status'] == 'applied':
                raise HTTPException(409, "Đề xuất đã lưu thành bản trích; dùng phiên bản mới để sửa tiếp.")
            db.execute("UPDATE source_proposals SET status='discarded' WHERE id=?", (proposal_id,))
            return {'id': proposal_id, 'status': 'discarded'}

    @app.post('/api/source-proposals/{proposal_id}/apply')
    def apply(proposal_id: str, body: VisionRequest, owner=Depends(user)):
        with database.connection(write=True) as db:
            proposal = snapshot(db, proposal_id, owner)
            if proposal['status'] == 'applied':
                return source_snapshot(db, proposal['source_id'], owner, proposal['base_revision']+1)
            source = source_snapshot(db, proposal['source_id'], owner)
            if proposal['status'] != 'preview' or source['revision'] != proposal['base_revision'] or body.expected_revision != source['revision']:
                raise HTTPException(409, "Đề xuất không khớp bản trích hiện tại; bản đang có được giữ.")
            candidates, warnings = extract('vision.txt', proposal['text'].encode('utf-8'), ocr=False)
            visual = proposal.get('visual_review') or next((f['locator']['visual_review'] for f in proposal['before'] if f['locator'].get('visual_review')), {})
            scope_value=proposal['asset_id'] if proposal['page_kind']=='asset_id' else proposal['page']
            for f in candidates:
                if proposal['page_kind']=='asset_id':f['locator'].update(proposal['scope_locator'])
                f['locator'].update(type='vision_office_image' if proposal['page_kind']=='asset_id' else 'vision_page', **{proposal['page_kind']: scope_value}, location_scope='embedded_image_crop' if proposal['page_kind']=='asset_id' else 'full_page', model=proposal['model'], layout_unverified=True)
                if visual: f['locator']['visual_review'] = visual
                f['needs_review'] = True
                f['provenance'] = {'kind': 'manual_transcription' if proposal.get('manual_edit') else 'ai_transcription', 'proposal_id': proposal_id, 'transcription_prompt_version': proposal.get('transcription_prompt_version', 'legacy_unrecorded'), 'prior_fragment_ids': [x['id'] for x in proposal['before']]}
                if proposal.get('parent_proposal_id'):f['provenance']['parent_proposal_id']=proposal['parent_proposal_id']
            preserved = [f for f in source['fragments'] if f['locator'].get(proposal['page_kind']) != scope_value]
            fragments = preserved + candidates
            fragments.sort(key=lambda f: f['locator'].get('office_order',0) if proposal['page_kind']=='asset_id' else f['locator'].get(proposal['page_kind'], 1))
            if len(fragments) > MAX_FRAGMENTS or sum(len(f['text']) for f in fragments) > MAX_TEXT:
                raise HTTPException(422, "Bản đọc ảnh vượt giới hạn; không thay bản trích đang có.")
            revision = source['revision'] + 1
            for i, f in enumerate(fragments):
                f.update(id=f"{source['id']}:{revision}:{i}")
                f.setdefault('original_text', f['text'])
            metadata = source['metadata']
            metadata['warnings'] = list(dict.fromkeys(metadata['warnings'] + warnings + [proposal['warning']]))
            metadata['last_vision_review'] = {'model': proposal['model'], 'page': proposal['page'], 'asset_id':proposal.get('asset_id'), 'uncertain_spans': proposal['uncertain_spans'], 'proposal_id': proposal_id}
            db.execute('INSERT INTO extraction_revisions VALUES (?,?,?,?,?)', (source['id'], revision, dump(fragments), None, timestamp()))
            db.execute("UPDATE sources SET status='needs_review',metadata_json=? WHERE id=?", (dump(metadata), source['id']))
            db.execute("UPDATE source_proposals SET status='applied' WHERE id=?", (proposal_id,))
            return source_snapshot(db, source['id'], owner)
