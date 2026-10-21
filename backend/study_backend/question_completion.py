"""Append only missing questions through a creator-reviewed version proposal."""
import copy
import json
import uuid
from collections import Counter
from datetime import datetime, timezone

from fastapi import BackgroundTasks, Depends, HTTPException, Request
from pydantic import Field, model_validator

from .extract import explicit_sequence
from .generation_contract import QuestionRejected
from .language import language_instruction, validate_language
from .models import Lesson, Model, QUESTION_DRAFTS, validate_refs
from .ordering import verify_ordering
from .question_generation import question_prompt, question_stages, content_preferences, reject_duplicate_prompt
from .question_quality import verify_mcq_options
from . import job_progress
from . import chapter_evidence, subnet_reasoning, question_focus


def dump(value): return json.dumps(value, ensure_ascii=False)
def stamp(): return datetime.now(timezone.utc).isoformat()


class CompletionRequest(Model):
    expected_revision: int = Field(ge=1)
    unit_id: str = Field(min_length=1, max_length=100)
    stages: list[str] = Field(min_length=1, max_length=8)
    resume_job_id: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode='after')
    def unique_stages(self):
        if len(set(self.stages)) != len(self.stages):
            raise ValueError('Chọn mỗi câu còn thiếu đúng một lần.')
        return self


def missing_questions(unit, prefs, fragments):
    """Reconcile actual content, including manual edits, against approved counts.

    Stage names are request slots, not indices into old questions. Appending
    preserves the indices and stable identities of all existing questions.
    """
    stages = question_stages(prefs)
    actual = Counter(q['kind'] for q in unit['data']['questions'])
    old = {r['stage']: r for r in (unit.get('generation', {}).get('question_coverage') or {}).get('uncreated', [])}
    missing = []
    for kind in dict.fromkeys(kind for _, kind in stages):
        slots = [key for key, k in stages if k == kind]
        needed = max(0, len(slots) - actual[kind])
        # Preserve recorded slot names when possible; recover from older/manual
        # content without assuming its coverage metadata is still accurate.
        preferred = [key for key in slots if key in old]
        chosen = (preferred + [key for key in reversed(slots) if key not in preferred])[:needed]
        for key in slots:
            if key not in chosen: continue
            blocked = kind == 'ordering' and not explicit_sequence(fragments)
            rechecked = not blocked and old.get(key,{}).get('origin')=='backend_source_gate'
            reason = ('Nguồn của bài chưa có các bước theo trình tự rõ. Đối chiếu nguồn trước khi tạo câu sắp xếp.'
                      if blocked else 'Nguồn hiện có trình tự đánh số được nhận diện; có thể yêu cầu tạo và kiểm chứng riêng câu còn thiếu.'
                      if rechecked else old.get(key, {}).get('reason', 'Dạng câu này chưa đủ số lượng đã duyệt.'))
            missing.append({'stage': key, 'kind': kind, 'reason': reason,
                            'can_generate': not blocked, 'origin': 'backend_source_gate' if blocked else 'backend_source_rechecked' if rechecked else old.get(key, {}).get('origin', 'content_count')})
    return sorted(missing, key=lambda item: [key for key, _ in stages].index(item['stage']))


def register_question_completion(app, database, jobs, owned, user, course_snapshot, course_plan,
                                 unit_from, approved_fragments, active_test, generate_checked, chapters):
    def context(db, course_id, unit_id, owner, revision=None):
        owned(db, 'courses', course_id, owner)
        if active_test(db, owner, course_id):
            raise HTTPException(403, 'Nộp/hủy lượt kiểm tra hoặc rời phòng trước khi bổ sung câu hỏi.')
        course = course_snapshot(db, course_id, owner)
        if revision is not None and course['revision'] != revision:
            raise HTTPException(409, 'Khóa đã đổi; tải lại trước khi bổ sung câu hỏi.')
        unit = unit_from(course, unit_id, ready=True)
        plan = course_plan(db, course, owner, unit)
        if plan['status'] != 'approved': raise HTTPException(409, 'Nguồn của bài chưa được duyệt.')
        fragments = approved_fragments(db, plan, owner, unit['source_refs'])
        return course, unit, plan, json.loads(plan['preferences_json']), fragments

    @app.get('/api/courses/{course_id}/question-completion')
    def options(course_id: str, unit_id: str, owner=Depends(user)):
        with database.connection() as db:
            course, unit, plan, prefs, fragments = context(db, course_id, unit_id, owner)
            missing = missing_questions(unit, prefs, fragments)
            return {'course_id': course_id, 'unit_id': unit_id, 'base_revision': course['revision'],
                    'requested_count': len(question_stages(prefs)), 'existing_count': len(unit['data']['questions']),
                    'missing': missing, 'available_slots': 8-len(unit['data']['questions']),
                    'source_id': plan['source_id'], 'extraction_revision': prefs['extraction_revision'],
                    'requires_preview': True, 'ai_called': False}

    @app.post('/api/courses/{course_id}/question-completion')
    async def complete(course_id: str, body: CompletionRequest, background: BackgroundTasks,
                       request: Request, owner=Depends(user)):
        with database.connection() as db:
            owned(db, 'courses', course_id, owner)
            if active_test(db, owner, course_id):
                raise HTTPException(403, 'Nộp/hủy lượt kiểm tra hoặc rời phòng trước khi bổ sung câu hỏi.')
        payload = {**body.model_dump(), 'course_id': course_id}
        identity = jobs.identity(request, 'question_completion', payload, owner=owner)
        cached = jobs.cached(owner, identity)
        if cached: return cached
        with database.connection() as db:
            course, unit, plan, prefs, fragments = context(db, course_id, body.unit_id, owner, body.expected_revision)
            chapter_fragments = approved_fragments(db, plan, owner)
            chapter_binding = chapters.binding(plan, owner, chapter_fragments)
            evidence_scope = None
            missing = missing_questions(unit, prefs, fragments)
            by_key = {item['stage']: item for item in missing}
            if not set(body.stages) <= set(by_key):
                raise HTTPException(409, 'Chỉ bổ sung những câu còn thiếu; câu đã có dùng sửa có phạm vi.')
            if any(not by_key[key]['can_generate'] for key in body.stages):
                raise HTTPException(422, 'Nguồn chưa có trình tự rõ cho câu sắp xếp; chưa gọi AI hoặc giữ Coin.')
            if len(body.stages) + len(unit['data']['questions']) > 8:
                raise HTTPException(422, 'Bài đã chạm giới hạn 8 câu; sửa phạm vi bộ câu trước khi bổ sung.')
            stages = [(item['stage'], item['kind']) for item in missing if item['stage'] in body.stages]
            saved, providers, rejections = {}, {}, {}
            question_focus_plan, stage_focus = None, {}
            reading = {k: unit['data'][k] for k in ('title', 'sections', 'cards', 'mindmap')}
            if body.resume_job_id:
                previous = owned(db, 'jobs', body.resume_job_id, owner)
                old_payload = json.loads(previous['payload_json'])
                if (previous['task'] != 'question_completion' or previous['status'] not in {'failed', 'cancelled'}
                    or any(old_payload.get(k) != payload[k] for k in ('course_id', 'unit_id', 'expected_revision', 'stages'))):
                    raise HTTPException(409, 'Phần đã lưu không khớp bài, phiên bản hoặc phạm vi câu đang bổ sung.')
                partial = json.loads(previous['partial_json'])
                evidence_scope = partial.get('evidence_scope')
                if evidence_scope:
                    fragments = chapter_evidence.validate(evidence_scope,chapter_fragments,unit,chapter_binding['id'])
                question_focus_plan = partial.get('question_focus_plan')
                stage_focus = partial.get('stage_focus', {})
                if question_focus_plan:
                    question_focus.validate(question_focus_plan, chapter_binding['id'], evidence_scope, unit, prefs, reading)
                question_focus.validate_requests(question_focus_plan, stage_focus)
                saved = {key: value for key, value in partial.get('questions', {}).items()
                         if key in body.stages and value.get('question')}
                providers = {key: partial.get('stage_providers', {}).get(key, old_payload.get('_provider', {})) for key in saved}
                rejections = partial.get('question_rejections', {})

        existing = unit['data']['questions']

        def check_candidate(key, drafted, prior):
            drafted = QUESTION_DRAFTS[by_key[key]['kind']].model_validate(drafted).model_dump()
            validate_refs(drafted, {f['id'] for f in fragments})
            validate_language(drafted, prefs)
            if drafted['question']:
                question = drafted['question']
                verify_mcq_options(question); verify_ordering(question, fragments)
                subnet_reasoning.check_question(question)
                if question['prompt'] in [q['prompt'] for q in prior]:
                    raise ValueError('Câu bổ sung lặp nguyên câu đã có; chưa áp dụng hoặc gọi lại tự động.')
                if prefs.get('difficulty'):
                    question.update(difficulty=prefs['difficulty'], difficulty_basis='creator_request_not_measured')
            return drafted

        # Revalidate saved stages against this immutable revision before reuse.
        prior = list(existing)
        for key, _ in stages:
            if key in saved:
                try:
                    saved[key] = check_candidate(key, saved[key], prior)
                except ValueError as exc:
                    raise HTTPException(409, 'Phần đã lưu không còn hợp lệ để dùng lại; tạo đề xuất mới trên bài hiện tại.') from exc
                prior.append(saved[key]['question'])

        async def work(job_id):
            nonlocal fragments,evidence_scope,question_focus_plan
            chapter_progress = chapters.describe(chapter_binding)
            chapter_total = chapter_progress['total_stages']
            reused = chapter_progress['saved_stages'] + len(saved)
            def checkpoint():
                with database.connection(write=True) as db:
                    jobs.check(db, job_id)
                    db.execute('UPDATE jobs SET partial_json=?,updated_at=? WHERE id=?',
                               (dump({'chapter_context': chapter_progress, 'evidence_scope': evidence_scope, 'questions': saved, 'stage_providers': providers, 'question_rejections': rejections,
                                      'requested_stages': body.stages, 'question_focus_plan': question_focus_plan,
                                      'stage_focus': stage_focus}), stamp(), job_id))
                    job_progress.chapter(db, job_id, chapter_progress)
                    jobs.saved_stages(db, job_id, chapter_total + len(stages), chapter_progress['saved_stages'] + len(saved), reused)
            def checkpoint_chapter(progress):
                nonlocal chapter_progress
                chapter_progress = progress
                checkpoint()
            chapter_progress, chapter_nodes = await chapters.prepare(chapter_binding, job_id, prefs, identity['provenance'], checkpoint_chapter)
            if not chapter_progress['complete']:
                result = {'course_id': course_id, 'unit_id': body.unit_id, 'base_revision': course['revision'],
                          'continuation_required': True, 'chapter_context': chapter_progress,
                          'message': 'Đã lưu tiến độ đọc chương; tiếp tục đọc đủ trước khi bổ sung câu hỏi.'}
                with database.connection(write=True) as db:
                    jobs.finish(db, job_id, result)
                return result
            instruction = 'Bổ sung câu còn thiếu cho đúng bài đã duyệt; không viết lại phần đọc, thẻ hoặc câu đã có. ' + dump({
                'preferences': content_preferences(prefs), 'unit': {'title': unit['title'], 'objective': unit['objective']}}) + language_instruction(prefs)
            fragments,evidence_scope = chapter_evidence.select(chapter_fragments,unit,prefs,
                chapters.summary(chapter_binding,chapter_nodes),chapter_binding['id'],evidence_scope)
            instruction += chapters.instruction(chapter_binding, chapter_nodes, evidence_scope['focus_source_refs']) + chapter_evidence.instruction(evidence_scope)
            question_focus_plan = question_focus.prepare(chapter_binding['id'], evidence_scope, unit, prefs, reading,
                chapters.summary(chapter_binding, chapter_nodes), fragments, question_focus_plan)
            checkpoint()
            for key, kind in stages:
                if key in saved: continue
                rejections.pop(key, None)
                prior = existing + [v['question'] for v in saved.values() if v.get('question')]
                question_focus.record_request(question_focus_plan, stage_focus, key, job_id)
                checkpoint()
                try:
                    drafted = await generate_checked(QUESTION_DRAFTS[kind], question_prompt(instruction, kind, unit['objective'], prior) + question_focus.instruction(question_focus_plan, key), fragments)
                    reject_duplicate_prompt(drafted,prior)
                except QuestionRejected as exc:
                    drafted = {'question': None, 'reason': str(exc)}
                    rejections[key] = exc.details
                saved[key] = check_candidate(key, drafted, prior)
                providers[key] = identity['provenance']
                checkpoint()
            added = [saved[key]['question'] for key, _ in stages if saved[key].get('question')]
            if not added:
                raise ValueError('Chưa có câu bổ sung đối chiếu được với nguồn. Bài đang học giữ nguyên; lý do từng câu đã lưu, chưa tự gọi lại.')
            content = copy.deepcopy(course['content'])
            target = next(u for u in content['units'] if u['id'] == body.unit_id)
            target['source_refs'] = evidence_scope['input_source_refs']
            target['data'] = Lesson.model_validate({**target['data'], 'questions': existing + added}).model_dump()
            generation = target.setdefault('generation', {})
            generation['evidence_scope'] = evidence_scope
            before_coverage = copy.deepcopy(generation.get('question_coverage'))
            filled = {key for key, _ in stages if saved[key].get('question')}
            generation['question_coverage'] = {**(before_coverage or {}),
                'uncreated': [item for item in (before_coverage or {}).get('uncreated', []) if item['stage'] not in filled]}
            remaining = missing_questions(target, prefs, fragments)
            for item in remaining:
                key = item['stage']
                if key in saved and not saved[key].get('question'):
                    item.update(reason=saved[key]['reason'], origin=rejections.get(key, {}).get('origin', 'model_declined'))
                    if key in rejections: item['code'] = rejections[key]['code']
                item.pop('can_generate', None)
            coverage = {'requested_count': len(question_stages(prefs)), 'generated_count': len(target['data']['questions']),
                        'requested_types': list(dict.fromkeys(kind for _, kind in question_stages(prefs))),
                        'generated_types': list(dict.fromkeys(q['kind'] for q in target['data']['questions'])),
                        'complete': not remaining, 'uncreated': remaining}
            generation['question_coverage'] = coverage
            generation.setdefault('question_completion_history', []).append({
                'job_id': job_id, 'base_revision': course['revision'], 'provider': identity['provenance'],
                'stage_providers': providers, 'requested_stages': body.stages,
                'chapter_context': chapter_progress,
                'evidence_scope': evidence_scope,
                'question_focus_plan': question_focus_plan, 'stage_focus': stage_focus,
                'added_stages': [key for key, _ in stages if saved[key].get('question')],
                'source_id': plan['source_id'], 'extraction_revision': prefs['extraction_revision'],
                'source_refs': evidence_scope['input_source_refs'], 'resumed_from_job_id': body.resume_job_id, 'created_at': stamp()})
            proposal_id = uuid.uuid4().hex
            value = {'before': {'questions': existing, 'question_coverage': before_coverage, 'source_refs':unit['source_refs']},
                     'after': {'questions': target['data']['questions'], 'question_coverage': coverage,
                               'source_refs':target['source_refs'],'evidence_scope':evidence_scope}, 'content': content}
            result = {'proposal_id': proposal_id, 'base_revision': course['revision'], 'requires_apply': True,
                      'added_count': len(added), 'question_coverage': coverage}
            with database.connection(write=True) as db:
                jobs.check(db, job_id)
                # A concurrent change cannot be overwritten: preview stays tied
                # to the old base and the existing apply endpoint rejects it.
                db.execute('INSERT INTO revision_proposals VALUES (?,?,?,?,?,?,?,?,?)',
                           (proposal_id, owner, course_id, course['revision'],
                            dump({'target': 'question_completion', 'unit_id': body.unit_id, 'stages': body.stages}),
                            'Bổ sung riêng các câu còn thiếu; giữ nội dung và lịch sử đã học.', dump(value), 'preview', stamp()))
                jobs.finish(db, job_id, result)
            return result
        return jobs.create(owner, 'question_completion', payload, background, work, identity)
