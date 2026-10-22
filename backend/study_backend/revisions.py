"""Creator-only future-plan/revert previews with immutable historical snapshots."""
import copy
import json
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import Depends, HTTPException
from pydantic import Field, model_validator

from .models import Model, Outline
from .setup import PlanPreferences
from .source_limits import MAX_FRAGMENTS
from .chapter_evidence import focus_refs


class FutureUnit(Model):
    unit_id: str
    title: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=1, max_length=1000)
    source_refs: list[str] = Field(min_length=1, max_length=12)
    source_id: str | None = Field(default=None, min_length=1, max_length=100)
    expected_extraction_revision: int | None = Field(default=None, ge=1)
    chapter_fragment_ids: list[str] | None = Field(default=None,min_length=1,max_length=MAX_FRAGMENTS,
        description='Entire approved chapter context to read, including the smaller unit source_refs. Required for a changed source when focus does not cover the whole file.')

    @model_validator(mode='after')
    def explicit_source_version(self):
        if (self.source_id is None) != (self.expected_extraction_revision is None):
            raise ValueError('Chọn cả tài liệu và phiên bản trích khi đổi nguồn bài.')
        if not self.title.strip() or not self.objective.strip() or not self.unit_id.strip():
            raise ValueError('Bài, tiêu đề và mục tiêu không được chỉ có khoảng trắng.')
        return self


class FuturePreferences(Model):
    subject: str | None = Field(default=None, min_length=1, max_length=200)
    goal: str | None = Field(default=None, min_length=1, max_length=1000)
    instructions: str | None = Field(default=None, max_length=2000)
    language: str | None = None
    initial_mode: str | None = None
    unlock_policy: str | None = None
    difficulty: str | None = None
    question_types: list[str] | None = None
    question_count: int | None = None
    card_count: int | None = None
    terms_to_keep: list[str] | None = None
    chapter_priorities: list[str] | None = None
    teacher_notes: str | None = None
    user_notes: str | None = None


class FutureEdit(Model):
    expected_revision: int = Field(ge=1)
    units: list[FutureUnit] = Field(min_length=1, max_length=6)
    preferences: FuturePreferences = Field(default_factory=FuturePreferences)
    remaining_order: list[str] | None = Field(default=None, max_length=6)
    request: str = Field(min_length=1, max_length=2000)


class Revert(Model):
    expected_revision: int = Field(ge=1)
    target_revision: int = Field(ge=1)
    unit_id: str | None = None
    request: str = Field(default='Quay lại bản đã chọn, giữ lịch sử lượt cũ.', min_length=1, max_length=2000)


class UnlockPolicyEdit(Model):
    expected_revision: int = Field(ge=1)
    unlock_policy: Literal['locked', 'open']


def stamp(): return datetime.now(timezone.utc).isoformat()
def dump(value): return json.dumps(value, ensure_ascii=False)


def register_revisions(app, database, course_snapshot, source_snapshot, owned, active_test, reader_course, user):
    def creator(db, course_id, owner):
        owned(db, 'courses', course_id, owner)
        if active_test(db, owner, course_id):
            raise HTTPException(403, 'Nộp/hủy lượt kiểm tra trước khi xem đáp án hoặc sửa bản khóa.')

    def bindings(db, owner, course, content=None, plan_id=None):
        values = []
        for unit in (content or course['content'])['units']:
            plan = owned(db, 'plans', unit.get('source_plan_id', plan_id or course['plan_id']), owner)
            prefs = json.loads(plan['preferences_json'])
            source = source_snapshot(db, plan['source_id'], owner, prefs['extraction_revision'])
            values.append({'unit_id': unit['id'], 'title': unit['title'], 'generated': bool(unit.get('data')),
                           'plan_id': plan['id'], 'source_id': plan['source_id'], 'source_name': source['metadata']['name'],
                           'extraction_revision': source['revision'], 'source_refs': unit['source_refs'],
                           'focus_source_refs':focus_refs(unit),
                           'chapter_scope':{'selected_fragments':len(prefs['fragment_ids']),
                               'source_fragments':len(source['fragments']),
                               'full_source':set(prefs['fragment_ids'])=={f['id'] for f in source['fragments']},
                               'method':prefs.get('chapter_scope_method','approved_plan_selection'),
                               'chapter_boundary_inferred':False},
                           'preferences': prefs})
        return values

    def save(db, owner, course, scope, request, before, content, plan_id, plan_ids=None, source_guards=None):
        proposal_id = uuid.uuid4().hex
        value = {'before': before, 'after': content, 'content': content, 'plan_id': plan_id,
                 'plan_ids': plan_ids or [plan_id], 'source_guards': source_guards or [],
                 'source_bindings': {'before': bindings(db, owner, course),
                                     'after': bindings(db, owner, course, content, plan_id)}}
        db.execute('INSERT INTO revision_proposals VALUES (?,?,?,?,?,?,?,?,?)', (proposal_id, owner, course['id'], course['revision'], dump(scope), request,
            dump(value), 'preview', stamp()))
        return {'proposal_id': proposal_id, 'base_revision': course['revision'], 'status': 'preview', 'requires_apply': True}

    @app.get('/api/courses/{course_id}/source-bindings')
    def source_bindings(course_id: str, owner=Depends(user)):
        with database.connection() as db:
            creator(db, course_id, owner)
            course = course_snapshot(db, course_id, owner)
            values = bindings(db, owner, course)
            for value in values:
                latest = source_snapshot(db, value['source_id'], owner)
                value.update(latest_extraction_revision=latest['revision'], latest_reviewed=latest['reviewed'],
                             can_change_source=not value['generated'])
            return {'course_id': course_id, 'revision': course['revision'], 'units': values}

    @app.get('/api/courses/{course_id}/revisions')
    def revisions(course_id: str, owner=Depends(user)):
        with database.connection() as db:
            owned(db, 'courses', course_id, owner)
            return [{'revision': r['revision'], 'plan_id': r['plan_id'], 'created_at': r['created_at'],
                     'units': [{'id': u['id'], 'title': u['title'], 'generated': bool(u.get('data'))} for u in json.loads(r['content_json'])['units']]}
                    for r in db.execute('SELECT * FROM course_revisions WHERE course_id=? ORDER BY revision DESC', (course_id,))]

    @app.get('/api/courses/{course_id}/revisions/{revision}')
    def revision(course_id: str, revision: int, editor: bool = False, owner=Depends(user)):
        with database.connection() as db:
            owned(db, 'courses', course_id, owner)
            if editor: creator(db, course_id, owner)
            value = course_snapshot(db, course_id, owner, revision)
            return value if editor else reader_course(value)

    @app.post('/api/courses/{course_id}/revert-preview')
    def revert(course_id: str, body: Revert, owner=Depends(user)):
        with database.connection(write=True) as db:
            creator(db, course_id, owner)
            current = course_snapshot(db, course_id, owner)
            if current['revision'] != body.expected_revision or body.target_revision >= current['revision']:
                raise HTTPException(409, 'Chọn bản cũ và đúng phiên bản hiện tại để xem trước hoàn tác.')
            prior = course_snapshot(db, course_id, owner, body.target_revision)
            content = copy.deepcopy(prior['content'] if body.unit_id is None else current['content'])
            plan_id = prior['plan_id'] if body.unit_id is None else current['plan_id']
            if body.unit_id is not None:
                old = next((u for u in prior['content']['units'] if u['id'] == body.unit_id), None)
                index = next((i for i,u in enumerate(content['units']) if u['id'] == body.unit_id), None)
                if old is None or index is None:
                    raise HTTPException(422, 'Bài không tồn tại ở cả hai phiên bản; chọn hoàn tác toàn khóa để duyệt thay đổi cấu trúc.')
                content['units'][index] = copy.deepcopy(old)
                content['units'][index]['source_plan_id'] = old.get('source_plan_id', prior['plan_id'])
            return save(db, owner, current, {'target':'revert','unit_id':body.unit_id,'target_revision':body.target_revision}, body.request, current['content'], content, plan_id)

    @app.post('/api/courses/{course_id}/unlock-policy-preview')
    def unlock_policy(course_id: str, body: UnlockPolicyEdit, owner=Depends(user)):
        """The creator may switch between opening lessons one by one and opening all of them, any time after creating the course."""
        with database.connection(write=True) as db:
            creator(db, course_id, owner)
            course = course_snapshot(db, course_id, owner)
            if course['revision'] != body.expected_revision:
                raise HTTPException(409, 'Khóa đã đổi; tải lại trước khi đổi cách mở bài.')
            if course['content']['unlock_policy'] == body.unlock_policy:
                raise HTTPException(409, 'Khóa đang dùng cách mở bài này rồi.')
            content = copy.deepcopy(course['content'])
            # Only the order rule changes; lessons, sources and results stay as they are.
            content['unlock_policy'] = body.unlock_policy
            if isinstance(content.get('preferences'), dict):
                content['preferences']['unlock_policy'] = body.unlock_policy
            for unit in content['units']:
                unit.pop('completed', None)
                unit.pop('unlocked', None)
            request = 'Mở mọi bài để học tự do' if body.unlock_policy == 'open' else 'Mở dần từng bài sau lượt luyện'
            return save(db, owner, course, {'target': 'unlock_policy', 'unlock_policy': body.unlock_policy}, request, course['content'], content, course['plan_id'])

    @app.post('/api/courses/{course_id}/future-plan-preview')
    def future(course_id: str, body: FutureEdit, owner=Depends(user)):
        with database.connection(write=True) as db:
            creator(db, course_id, owner)
            course = course_snapshot(db, course_id, owner)
            if course['revision'] != body.expected_revision:
                raise HTTPException(409, 'Khóa đã đổi; tải lại trước khi sửa phần chưa tạo.')
            content = copy.deepcopy(course['content'])
            ids = [u.unit_id for u in body.units]
            if len(ids) != len(set(ids)):
                raise HTTPException(422, 'Không lặp bài cần sửa.')
            # Every untouched unit keeps its effective plan, including drafts.
            # Changing the course default must not move old lessons to new sources.
            for unit in content['units']:
                unit.setdefault('source_plan_id', course['plan_id'])
            patch = body.preferences.model_dump(exclude_unset=True)
            plan_ids, source_guards, source_changed = [], [], False
            for requested in body.units:
                unit = next((u for u in content['units'] if u['id'] == requested.unit_id), None)
                if unit is None or unit.get('data'):
                    raise HTTPException(409, 'Chỉ sửa phác thảo chưa tạo ở đây; bài đã có dùng bản sửa bài/câu/thẻ.')
                plan = owned(db, 'plans', unit['source_plan_id'], owner)
                previous = json.loads(plan['preferences_json'])
                source_id = requested.source_id or plan['source_id']
                if requested.source_id is not None:
                    source = source_snapshot(db, source_id, owner)
                    if source['revision'] != requested.expected_extraction_revision:
                        raise HTTPException(409, 'Bản trích đã đổi; xem và duyệt lại đúng nguồn trước khi đổi bài.')
                    source_guards.append({'source_id': source_id, 'extraction_revision': source['revision']})
                else:
                    source = source_snapshot(db, source_id, owner, previous['extraction_revision'])
                if not source['reviewed']:
                    raise HTTPException(409, 'Đối chiếu và xác nhận bản trích trước khi dùng cho bài chưa tạo.')
                available = {f['id'] for f in source['fragments']}
                if len(set(requested.source_refs)) != len(requested.source_refs) or not set(requested.source_refs) <= available:
                    raise HTTPException(422, 'Đoạn không thuộc tài liệu và bản trích đã chọn cho bài này.')
                same_source = source_id == plan['source_id'] and source['revision'] == previous['extraction_revision']
                if requested.chapter_fragment_ids is not None:
                    chapter_refs=requested.chapter_fragment_ids
                    if len(set(chapter_refs))!=len(chapter_refs) or not set(chapter_refs)<=available or not set(requested.source_refs)<=set(chapter_refs):
                        raise HTTPException(422,'Phạm vi chương phải thuộc đúng bản nguồn và chứa toàn bộ trọng tâm bài.')
                    chapter_method='explicit_chapter_selection'
                elif same_source and set(requested.source_refs)<=set(previous['fragment_ids']):
                    chapter_refs=previous['fragment_ids']
                    chapter_method='preserved_approved_chapter'
                elif set(requested.source_refs)==available:
                    chapter_refs=requested.source_refs
                    chapter_method='focus_covers_source'
                else:
                    raise HTTPException(422,{'code':'CHAPTER_SCOPE_REQUIRED',
                        'message':'Chọn thêm chapter_fragment_ids cho toàn phạm vi chương cần AI đọc. source_refs chỉ là trọng tâm bài; chưa tự coi vài đoạn là toàn chương hoặc gửi toàn tài liệu.'})
                if any(f['locator'].get('unreadable_math') for f in source['fragments'] if f['id'] in chapter_refs):
                    raise HTTPException(422,'Phạm vi chương còn công thức chưa đọc được; sửa hoặc chọn lại chương trước khi duyệt.')
                unit.update(title=requested.title, objective=requested.objective, source_refs=requested.source_refs)
                candidate = {k: v for k, v in previous.items() if k in PlanPreferences.model_fields}
                candidate.update(patch, source_id=source_id, expected_extraction_revision=source['revision'],
                                 fragment_ids=chapter_refs)
                source_changed = source_changed or not same_source
                candidate['excluded_fragment_ids'] = [r for r in previous.get('excluded_fragment_ids', [])
                                                       if r in available and r not in chapter_refs] if same_source else []
                try:
                    prefs = PlanPreferences.model_validate(candidate).model_dump()
                except ValueError as exc:
                    raise HTTPException(422, 'Cấu hình bài chưa hợp lệ; kiểm tra môn/ngôn ngữ/số/dạng/phạm vi trước khi duyệt.') from exc
                prefs['extraction_revision'] = source['revision']
                prefs['chapter_scope_method'] = chapter_method
                outline = Outline.model_validate({'title': content['title'], 'units': [{k: unit[k] for k in ['title','objective','source_refs']}]}).model_dump()
                new_plan = uuid.uuid4().hex
                db.execute('INSERT INTO plans VALUES (?,?,?,?,?,?,?,?)', (new_plan, owner, source_id, dump(prefs), dump({**outline, 'version': 1}), 'proposal_preview', stamp(), None))
                unit['source_plan_id'] = new_plan
                plan_ids.append(new_plan)
                if len(plan_ids) == 1:
                    content['preferences'] = prefs
            if body.remaining_order is not None:
                remaining = [u for u in content['units'] if not u.get('data')]
                if len(body.remaining_order) != len(set(body.remaining_order)) or set(body.remaining_order) != {u['id'] for u in remaining}:
                    raise HTTPException(422, 'Thứ tự phải gồm mỗi bài chưa tạo đúng một lần; không đổi bài đã tạo.')
                ordered = iter([next(u for u in remaining if u['id']==i) for i in body.remaining_order])
                content['units'] = [u if u.get('data') else next(ordered) for u in content['units']]
            if 'unlock_policy' in patch:
                content['unlock_policy'] = content['preferences']['unlock_policy']
            return save(db, owner, course, {'target': 'future_plan', 'unit_ids': ids,
                        'preferences_unit_ids': ids, 'source_revision_unchanged': not source_changed,
                        'course_unlock_policy_changed': content['unlock_policy'] != course['content']['unlock_policy']},
                        body.request, course['content'], content, plan_ids[0], plan_ids, source_guards)
