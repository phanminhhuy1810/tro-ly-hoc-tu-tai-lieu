"""Source-backed subject suggestions and missing-only setup questions."""
import json
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import BackgroundTasks, Depends, HTTPException, Request
from pydantic import Field, model_validator

from .models import Model
from .source_limits import MAX_FRAGMENTS

MODES = ['learn', 'cards', 'practice']
TYPES = ['mcq', 'cloze', 'matching', 'ordering', 'short_answer']


class SubjectSuggestion(Model):
    subject: str = Field(min_length=1, max_length=200)
    evidence: str = Field(min_length=1, max_length=1000)
    source_refs: list[str] = Field(min_length=1, max_length=12)


class SubjectAnalysis(Model):
    subjects: list[SubjectSuggestion] = Field(min_length=1, max_length=3)
    recommended_mode: Literal['learn', 'cards', 'practice']
    reason: str = Field(min_length=1, max_length=1000)
    uncertainty: str = Field(max_length=1000)


class SourceAnalysisRequest(Model):
    expected_revision: int = Field(ge=1)
    fragment_ids: list[str] = Field(min_length=1, max_length=16)


class PlanPreferences(Model):
    source_id: str
    subject: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1, max_length=1000)
    instructions: str = Field(default='', max_length=2000)
    language: Literal['vi', 'en', 'source'] = 'vi'
    fragment_ids: list[str] = Field(min_length=1, max_length=MAX_FRAGMENTS)
    unlock_policy: Literal['locked', 'open'] = 'locked'
    initial_mode: Literal['learn', 'cards', 'practice'] = 'learn'
    expected_extraction_revision: int | None = Field(default=None, ge=1)
    excluded_fragment_ids: list[str] = Field(default_factory=list, max_length=MAX_FRAGMENTS)
    chapter_priorities: list[str] = Field(default_factory=list, max_length=20)
    difficulty: Literal['basic', 'applied', 'hard'] | None = None
    question_types: list[Literal['mcq', 'cloze', 'matching', 'ordering', 'short_answer']] = Field(default_factory=lambda: TYPES.copy(), min_length=1, max_length=5)
    question_count: int | None = Field(default=None, ge=1, le=8, description='Planned per unit; missing source can result in fewer usable types')
    card_count: int | None = Field(default=None, ge=1, le=6)
    target_language: str = Field(default='', max_length=80)
    terms_to_keep: list[str] = Field(default_factory=list, max_length=30)
    teacher_notes: str = Field(default='', max_length=2000)
    user_notes: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def valid_scope_and_distribution(self):
        if not self.subject.strip() or not self.goal.strip():
            raise ValueError('Cần xác nhận môn và mục tiêu, không chỉ nhập khoảng trắng.')
        if len(set(self.question_types)) != len(self.question_types):
            raise ValueError('Không lặp dạng câu.')
        if self.question_count is not None and self.question_count < len(self.question_types):
            raise ValueError('Số câu ít hơn số dạng đã chọn; chọn ít dạng hoặc tăng số câu trước khi duyệt.')
        if set(self.fragment_ids) & set(self.excluded_fragment_ids):
            raise ValueError('Một đoạn không thể vừa học vừa bỏ qua.')
        if any(not t.strip() or len(t) > 100 for t in self.terms_to_keep + self.chapter_priorities):
            raise ValueError('Thuật ngữ/ưu tiên cần 1–100 ký tự mỗi mục.')
        return self


class SetupChoices(Model):
    source_id: str
    expected_revision: int = Field(ge=1)
    subject: str = Field(default='', max_length=200)
    goal: str = Field(default='', max_length=1000)
    initial_mode: Literal['learn', 'cards', 'practice', 'unknown'] | None = None
    language: Literal['vi', 'en', 'source', 'unknown'] | None = None
    fragment_ids: list[str] = Field(default_factory=list, max_length=MAX_FRAGMENTS)


def preview_modes(outline, preferences):
    types = preferences.get('question_types') or TYPES
    count = preferences.get('question_count') or len(types)
    cards = preferences.get('card_count') or 2
    return {'initial_mode': preferences.get('initial_mode', 'learn'), 'shared_course': True,
        'needs_approval': True, 'counts_are_targets_not_generated': True,
        'learn': {'units': [{'title': u['title'], 'objective': u['objective'], 'source_refs': u['source_refs']} for u in outline['units']], 'practice_after_unit': True},
        'cards': {'groups': [{'title': u['title'], 'planned_cards': cards, 'source_refs': u['source_refs']} for u in outline['units']]},
        'practice': {'groups': [{'title': u['title'], 'planned_questions': count, 'types': types, 'difficulty_requested': preferences.get('difficulty')} for u in outline['units']], 'warning': 'Chỉ tạo loại có đủ nguồn; không bịa để đủ số. Mức độ là đề xuất, chưa đo năng lực.'}}


def register_setup(app, database, jobs, source_snapshot, owned, user, generate_checked):
    def fragments(source, refs):
        allowed = {f['id'] for f in source['fragments']}
        if len(set(refs)) != len(refs) or any(r not in allowed for r in refs):
            raise HTTPException(422, 'Phạm vi không thuộc bản trích đang xác nhận.')
        return [{'id': f['id'], 'text': f['text'], 'locator': f['locator']} for f in source['fragments'] if f['id'] in refs]

    @app.post('/api/sources/{source_id}/analyze')
    async def analyze(source_id: str, body: SourceAnalysisRequest, background: BackgroundTasks, request: Request, owner=Depends(user)):
        payload = {**body.model_dump(), 'source_id': source_id}
        identity = jobs.identity(request, 'subject_analysis', payload, owner=owner)
        prior = jobs.cached(owner, identity)
        if prior: return prior
        with database.connection() as db:
            source = source_snapshot(db, source_id, owner)
            if source['revision'] != body.expected_revision or not source['reviewed']:
                raise HTTPException(409, 'Đối chiếu và xác nhận đúng bản trích trước khi gợi ý môn.')
            selected = fragments(source, body.fragment_ids)
            if any(f['locator'].get('unreadable_math') for f in selected):
                raise HTTPException(422,'Sửa hoặc bỏ công thức chưa đọc được trước khi nhờ AI gợi ý môn.')

        async def work(job_id):
            value = await generate_checked(SubjectAnalysis, 'Đề xuất 1–3 môn từ các đoạn đã đối chiếu; evidence nêu dấu hiệu trong nguồn và source_refs. Đề xuất một trong learn/cards/practice và lý do. Đây là suy luận để người học được sửa, không phải xác nhận môn hoặc tạo bài. Nếu phạm vi có thể gồm nhiều môn hoặc chưa đủ, nói rõ trong uncertainty. Chỉ trả JSON theo schema.', selected)
            analysis_id = uuid.uuid4().hex
            value.update(scope_fragment_ids=body.fragment_ids, source_id=source_id, extraction_revision=body.expected_revision, inference_not_confirmation=True, scope_limited=len(selected) < len(source['fragments']))
            with database.connection(write=True) as db:
                jobs.check(db, job_id)
                db.execute('INSERT INTO source_analyses VALUES (?,?,?,?,?,?)', (analysis_id, owner, source_id, body.expected_revision, json.dumps(value, ensure_ascii=False), datetime.now(timezone.utc).isoformat()))
                result = {'analysis_id': analysis_id}
                jobs.finish(db, job_id, result)
            return result
        return jobs.create(owner, 'subject_analysis', payload, background, work, identity)

    @app.get('/api/sources/{source_id}/analysis')
    def analysis(source_id: str, owner=Depends(user)):
        with database.connection() as db:
            source = source_snapshot(db, source_id, owner)
            row = db.execute('SELECT content_json FROM source_analyses WHERE source_id=? AND owner_id=? AND extraction_revision=? ORDER BY created_at DESC LIMIT 1', (source_id, owner, source['revision'])).fetchone()
            return {'status': 'suggested', **json.loads(row[0])} if row else {'status': 'not_analyzed', 'extraction_revision': source['revision'], 'subjects': []}

    @app.post('/api/setup/clarify')
    def clarify(body: SetupChoices, owner=Depends(user)):
        with database.connection() as db:
            source = source_snapshot(db, body.source_id, owner)
            if source['revision'] != body.expected_revision or not source['reviewed']:
                raise HTTPException(409, 'Xác nhận bản trích trước khi chọn nhu cầu.')
            fragments(source, body.fragment_ids)
            row = db.execute('SELECT content_json FROM source_analyses WHERE source_id=? AND extraction_revision=? AND owner_id=? ORDER BY created_at DESC LIMIT 1', (body.source_id, body.expected_revision, owner)).fetchone()
            suggested = json.loads(row[0]) if row else {}
        questions = []
        def missing(key, text, options, default):
            value = getattr(body, key)
            if not value or value == 'unknown':
                questions.append({'field': key, 'question': text, 'options': options, 'free_input': key in {'subject', 'goal'}, 'suggested_default': default, 'requires_confirmation': True})
        subjects = [x['subject'] for x in suggested.get('subjects', [])]
        missing('subject', 'Bạn học môn nào? Có thể đổi đề xuất hoặc tự nhập.', subjects, subjects[0] if subjects else None)
        missing('goal', 'Bạn cần học từ đầu, ôn phần quan trọng hay thử mức hiểu?', ['Hiểu từ đầu', 'Ôn phần quan trọng', 'Thử mức hiểu'], 'Hiểu từ đầu')
        missing('initial_mode', 'Bạn muốn bắt đầu bằng cách nào?', MODES, suggested.get('recommended_mode', 'learn'))
        missing('language', 'Ngôn ngữ nội dung; thuật ngữ gốc được giữ riêng.', ['vi', 'en', 'source'], 'vi')
        missing('fragment_ids', 'Chọn đoạn/chương cần học. Phần bỏ qua không tự được đưa vào.', [f['id'] for f in source['fragments']], [f['id'] for f in source['fragments'][:5]])
        return {'questions': questions, 'can_create_preview': not questions, 'preferences': body.model_dump(), 'defaults_applied': False,
                'editable_suggestions': suggested, 'available_modes': MODES, 'content_language_independent_of_ui': True}
