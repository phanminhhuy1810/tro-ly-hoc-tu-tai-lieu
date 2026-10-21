"""Pinned multi-document sources and full-scope roadmaps without a giant AI call."""
import copy
import hashlib
import json
import uuid
from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from pydantic import Field

from .models import Model, Outline
from .source_context import fits, source_json, MAX_MODEL_SOURCE_JSON
from .setup import PlanPreferences
from .source_limits import MAX_COLLECTION_SOURCES, MAX_FRAGMENTS, MAX_TEXT, MAX_UNIT_FRAGMENTS
from .lifecycle import deleted


class SourceBinding(Model):
    source_id: str
    expected_revision: int = Field(ge=1)


class CollectionRequest(Model):
    name: str = Field(default='Tài liệu khóa học', min_length=1, max_length=180)
    sources: list[SourceBinding] = Field(min_length=2, max_length=MAX_COLLECTION_SOURCES)


def dump(value): return json.dumps(value, ensure_ascii=False)
def stamp(): return datetime.now(timezone.utc).isoformat()


def section_outline(source, selected, preferences):
    """Partition every selected excerpt. Labels are source locations, not AI claims."""
    from .source_scope_review import position_key
    # Keep one page/slide together when the actual request budget permits it.
    # Eight remains a packing target; the domain's existing twelve-ref ceiling
    # permits a single position with9–12 shapes instead of a heading-only unit.
    blocks=[]
    for fragment in selected:
        key=position_key(fragment,source['id'])
        if not blocks or key[1]=='fragment' or key!=position_key(blocks[-1][0],source['id']):blocks.append([])
        blocks[-1].append(fragment)
    bounded=[]
    project=lambda group:[{'id':f['id'],'text':f['text'],'locator':f['locator']} for f in group]
    for block in blocks:
        if len(block)<=12 and fits(project(block)):bounded.append(block);continue
        for fragment in block:
            if not bounded or len(bounded[-1])>=MAX_UNIT_FRAGMENTS or position_key(bounded[-1][0],source['id'])!=position_key(fragment,source['id']) or not fits(project(bounded[-1]+[fragment])):bounded.append([])
            bounded[-1].append(fragment)
    groups = []
    for block in bounded:
        fragment=block[0]
        component = fragment['locator'].get('component_source_id', source['id'])
        if (not groups or len(groups[-1])+len(block)>MAX_UNIT_FRAGMENTS or
                not fits(project(groups[-1]+block)) or
                groups[-1][0]['locator'].get('component_source_id', source['id']) != component):
            groups.append([])
        groups[-1].extend(block)
    english = preferences.language == 'en'
    units = []
    for index, group in enumerate(groups, 1):
        first, last = group[0]['locator'], group[-1]['locator']
        name = first.get('component_name') or source['metadata']['name']
        location = next((f"{label} {first[key]}–{last.get(key, first[key])}" for key,label in
                         [('page','pages' if english else 'trang'),('slide','slides' if english else 'slide')]
                         if key in first), f"{'Part' if english else 'Phần'} {index}")
        heading = first.get('heading', '').strip()
        native_title=' '.join(group[0]['text'].split())
        if not heading and first.get('slide') and first.get('shape')==1 and 2<=len(native_title)<=100 and native_title[-1] not in '.!?;':
            heading=native_title
        title = f"{heading or name} · {location}"[:200]
        objective = (f"Study {location} in {name}; check the source and practise this section."
                     if english else f"Học {location} trong {name}; đối chiếu nguồn và luyện nội dung của phần này.")
        units.append({'title': title, 'objective': objective[:1000], 'source_refs': [f['id'] for f in group]})
    return Outline.model_validate({'title': preferences.subject, 'units': units}).model_dump()


def register_source_collections(app, database, source_snapshot, user, save_source):
    @app.post('/api/sources/collection')
    def collection(body: CollectionRequest, owner=Depends(user)):
        if len({b.source_id for b in body.sources}) != len(body.sources) or not body.name.strip():
            raise HTTPException(422, 'Chọn các tài liệu khác nhau và đặt tên bộ nguồn.')
        sources = []
        with database.connection() as db:
            for binding in body.sources:
                source = source_snapshot(db, binding.source_id, owner)
                if source['revision'] != binding.expected_revision:
                    raise HTTPException(409, 'Một tài liệu đã đổi bản trích; tải lại trước khi gộp.')
                if source['metadata'].get('kind') == 'collection':
                    raise HTTPException(422, 'Chọn tài liệu gốc; chưa lồng bộ nguồn vào bộ nguồn khác.')
                sources.append(source)
        fragments, warnings, components = [], [], []
        for source in sources:
            components.append({'source_id': source['id'], 'extraction_revision': source['revision'],
                               'name': source['metadata']['name'], 'sha256': source['metadata']['sha256'],
                               'reviewed_at_collection': source['reviewed']})
            warnings.extend(f"{source['metadata']['name']}: {w}" for w in source['metadata'].get('warnings', []))
            for fragment in source['fragments']:
                value = copy.deepcopy(fragment)
                value['locator'].update(component_source_id=source['id'], component_revision=source['revision'],
                                        component_fragment_id=fragment['id'], component_name=source['metadata']['name'])
                value['collection_origin'] = {'source_id': source['id'], 'revision': source['revision'], 'fragment_id': fragment['id']}
                fragments.append(value)
        if not fragments or len(fragments) > MAX_FRAGMENTS or sum(len(f['text']) for f in fragments) > MAX_TEXT:
            raise HTTPException(422, 'Bộ nguồn vượt 2.000 đoạn hoặc 1.000.000 ký tự. Các tài liệu đã tải vẫn được giữ; chia thành các khóa theo chương.')
        manifest = {'kind': 'pinned_source_collection', 'name': body.name.strip(), 'sources': components}
        raw = dump(manifest).encode()
        # A repeated browser submission reopens the same pinned collection.
        with database.connection() as db:
            for row in db.execute('SELECT id,metadata_json FROM sources WHERE owner_id=?', (owner,)):
                if deleted(db,'source',row['id']):continue
                metadata = json.loads(row['metadata_json'])
                if metadata.get('kind') == 'collection' and metadata.get('sha256') == hashlib.sha256(raw).hexdigest():
                    return source_snapshot(db, row['id'], owner)
        warnings.append('Bộ nguồn giữ bản trích của từng tài liệu tại thời điểm gộp. Sửa tài liệu gốc sau đó không tự đổi khóa hoặc bộ nguồn này; cần tạo lại và duyệt phạm vi mới.')
        return save_source(owner, body.name.strip()+'.collection.json', raw, (fragments, warnings),
                           {'kind': 'collection', 'components': components, 'original_is_manifest': True})

    @app.post('/api/plans/strategy')
    def strategy(body: PlanPreferences, owner=Depends(user)):
        with database.connection() as db:
            source = source_snapshot(db,body.source_id,owner)
            if not source['reviewed'] or (body.expected_extraction_revision is not None and body.expected_extraction_revision!=source['revision']):
                raise HTTPException(409,'Xác nhận đúng bản trích trước khi chọn cách tạo lộ trình.')
            refs=set(body.fragment_ids)
            if len(refs)!=len(body.fragment_ids) or not refs<={f['id'] for f in source['fragments']}:
                raise HTTPException(422,'Phạm vi không thuộc bản trích đã duyệt.')
            selected=[{'id':f['id'],'text':f['text'],'locator':f['locator']} for f in source['fragments'] if f['id'] in refs]
        return {'method':'ai_outline' if len(selected)<=16 and fits(selected) else 'source_sections_not_ai',
                'selected_fragments':len(selected),'source_json_characters':len(source_json(selected)),
                'model_source_json_budget':MAX_MODEL_SOURCE_JSON,'ai_called':False}

    @app.post('/api/plans/from-source-sections')
    def source_sections(body: PlanPreferences, owner=Depends(user)):
        with database.connection(write=True) as db:
            source = source_snapshot(db, body.source_id, owner)
            if not source['reviewed'] or (body.expected_extraction_revision is not None and source['revision'] != body.expected_extraction_revision):
                raise HTTPException(409, 'Xác nhận đúng bản trích trước khi tạo lộ trình.')
            refs = set(body.fragment_ids)
            if len(refs) != len(body.fragment_ids) or not refs <= {f['id'] for f in source['fragments']}:
                raise HTTPException(422, 'Phạm vi không thuộc bản trích đã duyệt.')
            if not set(body.excluded_fragment_ids) <= {f['id'] for f in source['fragments']}:
                raise HTTPException(422, 'Phần bỏ qua không thuộc bản trích đã duyệt.')
            selected = [f for f in source['fragments'] if f['id'] in refs]
            if any(f['locator'].get('unreadable_math') for f in selected):
                raise HTTPException(422, 'Còn công thức chưa đọc được trong phạm vi. Sửa hoặc bỏ đoạn đó trước khi tạo bài.')
            if body.subject.casefold().strip() == 'unknown' or body.goal.casefold().strip() == 'unknown':
                raise HTTPException(409, 'Xác nhận môn và mục tiêu; lộ trình theo phần nguồn chưa tự nhận diện môn.')
            outline = section_outline(source, selected, body)
            prefs = {**body.model_dump(), 'extraction_revision': source['revision']}
            outline.update(version=1, method='source_sections_not_ai',
                           coverage={'selected_fragments': len(selected), 'assigned_fragments': len(selected),
                                     'not_selected_fragments': len(source['fragments'])-len(selected), 'ai_calls': 0})
            plan_id = uuid.uuid4().hex
            db.execute('INSERT INTO plans VALUES (?,?,?,?,?,?,?,?)',
                       (plan_id, owner, source['id'], dump(prefs), dump(outline), 'preview', stamp(), None))
            return {'id': plan_id, 'source_id': source['id'], 'preferences': prefs, 'outline': outline, 'status': 'preview'}
