"""Local first-course slice. Persistence and authorization live on the server."""
import asyncio
import copy
import hashlib
import json
import os
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import Field, StrictInt, StrictStr, model_validator

from .providers import configured_registry, register_providers
from .rooms import RoomStore, register_rooms
from .body_limit import BodyLimit
from .db import Database
from .extract import MAX_BYTES, explicit_sequence, extract
from .source_limits import MAX_TEXT, MAX_FRAGMENTS, MAX_AI_OUTLINE_FRAGMENTS, public_limits
from .jobs import JobCancelled, JobManager
from .learning import KINDS, LearningStore, PracticeRequest, grade_answer, public_question, question_item, register_learning
from .public_urls import fetch_article, parse_article
from .source_review import register_source_review
from .setup import PlanPreferences, preview_modes, register_setup
from .source_collections import register_source_collections
from .source_library import register_source_library
from .source_context import fits
from .source_ocr import register_source_ocr
from .revisions import register_revisions
from . import job_progress
from .job_events import register_job_events
from .feedback import register_feedback
from .community import CommunityStore, register_community
from .language import language_instruction, validate_language
from .economy import Economy, register_economy
from .activity import Activity, register_activity
from .ordering import verify_ordering
from .question_quality import verify_mcq_options
from .inline_help import register_inline_help
from .course_memory import MEMORY_RULE, memory_for_ai, register_course_memory
from .blueprint import register_blueprint
from .covers import register_covers
from .models import Card, ChatReply, Lesson, LessonReading, Model, Outline, Question, QUESTION_DRAFTS, grade
from .generation_contract import QuestionRejected
from .question_generation import question_prompt, question_stages, lesson_instruction, reject_duplicate_prompt, content_preferences
from .question_completion import register_question_completion
from .runtime_lock import workspace_lock
from .lifecycle import deleted, require_active, register_lifecycle
from .chapter_context import ChapterReader
from . import question_focus
from . import subnet_reasoning
from . import chapter_evidence
from . import correction_context, correction_prompt
from . import chat_prompt
from .accounts import register_accounts
from .gemini import ProviderError

ROOT = Path(__file__).resolve().parents[2]


def now():
    return datetime.now(timezone.utc).isoformat()


def new_id():
    return uuid.uuid4().hex


def dump(value):
    return json.dumps(value, ensure_ascii=False)


class TextSource(Model):
    name: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=MAX_TEXT)


class URLSource(Model):
    url: str = Field(min_length=1, max_length=3000)


class SourceReview(Model):
    expected_revision: int
    texts: list[str] = Field(min_length=1, max_length=MAX_FRAGMENTS)


class SourceTranscription(Model):
    expected_revision: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=MAX_TEXT)


Preferences = PlanPreferences


class PlanEdit(Model):
    expected_version: int
    outline: Outline


class Version(Model):
    expected_revision: int


class UnitRequest(Version):
    unit_id: str


class GenerateUnit(UnitRequest):
    resume_job_id: str | None = None


class Correction(UnitRequest):
    target: str = Field(pattern="^(lesson|question|card)$")
    index: int = Field(default=0, ge=0, le=20)
    request: str = Field(min_length=1, max_length=2000)
    replacement: dict | None = None
    resume_job_id: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode='after')
    def manual_does_not_resume_ai(self):
        if self.replacement is not None and self.resume_job_id is not None:
            raise ValueError('Chỉnh tay tạo preview trực tiếp; không gắn job AI để tiếp tục.')
        return self


class Answer(Model):
    item_id: str
    answer: str | list[StrictInt] | list[StrictStr] | dict[str, StrictStr]


class AnswerDraft(Answer):
    expected_version: int = 0


class QuestionReport(Model):
    expected_revision: int
    unit_id: str
    item_id: str
    reason: str = Field(min_length=1, max_length=2000)


class ChatRequest(Model):
    unit_id: str
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None
    item_id: str | None = None
    card_id: str | None = None


def create_app(db_path=None, storage_path=None, provider=None, extractor=None, article_fetcher=None, page_renderer=None, economy_enabled=True, clock=None, coin_policy=None, provider_registry=None, room_policy=None, native_ocr_reader=None, native_frame_counter=None):
    database = Database(str(db_path or ROOT / "backend/runtime/study.sqlite3"))
    storage = Path(storage_path or ROOT / "backend/runtime/sources")
    storage.mkdir(parents=True, exist_ok=True)
    ai = provider_registry if provider_registry is not None else configured_registry(provider)
    ai.database = database
    read_source = extractor or extract
    read_article = article_fetcher or fetch_article
    economy = Economy(database, economy_enabled, clock, coin_policy)
    jobs = JobManager(database, economy=economy, provider_router=ai)
    community = CommunityStore(database)

    async def generate_checked(schema, instruction, fragments):
        from .models import validate_refs
        if schema in {LessonReading, Lesson, Question, *QUESTION_DRAFTS.values()}:
            instruction += subnet_reasoning.instruction(fragments)
        value = schema.model_validate(await ai.generate(schema, instruction, fragments))
        validate_refs(value, {f["id"] for f in fragments})
        result = value.model_dump()
        candidates = ([result['question']] if result.get('question') else
                      result.get('questions', []) if 'questions' in result else [result] if result.get('kind') else [])
        for candidate in candidates:
            try:subnet_reasoning.check_question(candidate)
            except subnet_reasoning.SubnetClaimError as exc:
                raise QuestionRejected(exc,candidate) from exc
        return result

    chapters = ChapterReader(database, jobs, generate_checked)

    @asynccontextmanager
    async def lifespan(app):
        async def maintain_rooms():
            while True:
                await asyncio.to_thread(rooms.tick)
                await asyncio.sleep(1)
        with workspace_lock(database.path):
            jobs.recover_interrupted()
            ticker = asyncio.create_task(maintain_rooms())
            try:
                yield
            finally:
                ticker.cancel()
                await asyncio.gather(ticker, return_exceptions=True)

    app = FastAPI(title="Document study local slice", lifespan=lifespan)
    app.state.database = database
    app.state.jobs = jobs
    app.state.community = community
    app.state.economy = economy
    app.state.providers = ai
    rooms = RoomStore(database, clock, room_policy)
    app.state.rooms = rooms
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
    app.add_middleware(BodyLimit, limit=MAX_BYTES + 65536)

    @app.middleware("http")
    async def same_origin(request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and origin != f"{request.url.scheme}://{request.url.netloc}":
                from fastapi.responses import JSONResponse
                return JSONResponse({"detail": "Yêu cầu khác origin bị từ chối."}, status_code=403)
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def user(request: Request):
        token = request.cookies.get("study_session", "")
        with database.connection() as db:
            row = db.execute("SELECT user_id FROM auth_sessions WHERE token_hash=? AND expires_at>?", (hashlib.sha256(token.encode()).hexdigest(), int(time.time()))).fetchone()
        if not row:
            raise HTTPException(401, "Phiên học chưa có hoặc đã hết hạn.")
        return row["user_id"]

    def owned(db, table, item_id, owner):
        # table names come only from code, never request input.
        row = db.execute(f"SELECT * FROM {table} WHERE id=? AND owner_id=?", (item_id, owner)).fetchone()
        if not row:
            raise HTTPException(404, "Không tìm thấy nội dung trong không gian của bạn.")
        if table in {'sources','courses'}:
            require_active(db, 'source' if table=='sources' else 'course', item_id)
        elif table in {'plans','source_proposals','source_ocr_batches'}:
            require_active(db, 'source', row['source_id'])
        elif table in {'revision_proposals','publication_proposals'}:
            require_active(db, 'course', row['course_id'])
        return dict(row)

    def source_snapshot(db, source_id, owner, revision=None):
        source = owned(db, "sources", source_id, owner)
        metadata = json.loads(source['metadata_json'])
        # Old builds put the first excerpt in this field. It was not a subject
        # classifier. Only an actual scoped analysis may fill the suggestion.
        metadata['subject_suggestion'] = ''
        metadata.pop('subject_suggestion_is_inference', None)
        query = "SELECT * FROM extraction_revisions WHERE source_id=?"
        args = [source_id]
        if revision is not None:
            query += " AND revision=?"
            args.append(revision)
        row = db.execute(query + " ORDER BY revision DESC LIMIT 1", args).fetchone()
        if not row:
            if revision is not None:
                raise HTTPException(404, "Không có bản trích nguồn này.")
            return {"id": source_id, "metadata": metadata, "status": source["status"], "revision": 0, "reviewed": False, "fragments": []}
        analysis = db.execute('SELECT content_json FROM source_analyses WHERE source_id=? AND owner_id=? AND extraction_revision=? ORDER BY created_at DESC LIMIT 1', (source_id, owner, row['revision'])).fetchone()
        if analysis:
            metadata['subject_suggestion'] = json.loads(analysis[0])['subjects'][0]['subject']
            metadata['subject_suggestion_is_inference'] = True
        return {"id": source_id, "metadata": metadata, "status": source["status"], "revision": row["revision"], "reviewed": bool(row["reviewed_at"]), "fragments": json.loads(row["content_json"])}

    def course_snapshot(db, course_id, owner, revision=None):
        current = db.execute('SELECT * FROM courses WHERE id=?', (course_id,)).fetchone()
        if not current:
            raise HTTPException(404, 'Không có khóa trong không gian của bạn.')
        course = dict(current)
        role = community.role(db, course, owner)
        revision = revision or course["active_revision"]
        row = db.execute("SELECT * FROM course_revisions WHERE course_id=? AND revision=?", (course_id, revision)).fetchone()
        if not row:
            raise HTTPException(404, "Phiên bản khóa học không tồn tại.")
        content = json.loads(row["content_json"])
        complete = {r["unit_id"] for r in db.execute("SELECT unit_id FROM unit_completions WHERE owner_id=? AND course_id=?", (owner, course_id))}
        for i, unit in enumerate(content["units"]):
            unit["completed"] = unit["id"] in complete
            unit["unlocked"] = i == 0 or content["unlock_policy"] == "open" or content["units"][i-1]["id"] in complete
        return {"id": course_id, "revision": revision, "plan_id": row["plan_id"], "creator_id": course['owner_id'], 'access_role':role, "content": content}

    def unit_from(course, unit_id, ready=False):
        unit = next((x for x in course["content"]["units"] if x["id"] == unit_id), None)
        if not unit:
            raise HTTPException(404, "Bài chưa có nội dung đã tạo.")
        if not unit["unlocked"]:
            raise HTTPException(403, "Hoàn thành một lượt luyện bài trước để mở bài này.")
        if ready and not unit.get("data"):
            raise HTTPException(404, "Bài chưa có nội dung đã tạo.")
        return unit

    learning = LearningStore(database, course_snapshot, source_snapshot, unit_from, owned)
    app.state.learning = learning
    activity = Activity(database, economy, course_snapshot, community.ids, unit_from, learning.weak)
    app.state.activity = activity

    def reader_course(course):
        for unit in course["content"]["units"]:
            if unit.get("data"):
                unit["data"]["questions"] = [public_question(question_item(course["id"], unit["id"], i, q)) for i, q in enumerate(unit["data"]["questions"])]
            if course.get('access_role') == 'learner':
                unit.pop('generation', None)
                unit.pop('source_plan_id', None)
                if not unit['unlocked']: unit['data'] = None
            elif unit.get('generation'):
                # Planning notes can contain answer-bearing hints. Only the
                # guarded creator editor/job endpoints expose this audit data,
                # never the ordinary course view (including during a test).
                generation = unit['generation']
                generation.pop('question_focus_plan', None)
                generation.pop('stage_focus', None)
                for history in generation.get('question_completion_history', []):
                    history.pop('question_focus_plan', None)
                    history.pop('stage_focus', None)
        if course.get('access_role') == 'learner':
            course['plan_id'] = None
            course['content'].pop('preferences', None)
        return course

    def course_plan(db, course, actor, unit=None):
        return owned(db, 'plans', (unit or {}).get('source_plan_id', course['plan_id']), course.get('creator_id', actor))

    def active_exam(db, owner, course_id):
        return db.execute("SELECT 1 FROM study_sessions WHERE owner_id=? AND course_id=? AND exam=1 AND status='open' LIMIT 1", (owner, course_id)).fetchone() is not None

    def active_test(db, owner, course_id):
        return active_exam(db, owner, course_id) or rooms.active(db, owner, course_id)

    def reference_warnings(db, session):
        flags = {r['question_revision_id']: r['reason'] for r in db.execute("SELECT question_revision_id,reason FROM question_review_flags WHERE course_id=? AND state='needs_review'", (session['course_id'],))}
        return [{'item_id': q['id'], 'state': 'needs_review', 'reason': flags[q['question_revision_id']]} for q in json.loads(session['items_json']) if q.get('question_revision_id') in flags]

    def new_job(owner, task, payload, background, worker, identity, prepare=None):
        return jobs.create(owner, task, payload, background, worker, identity, prepare)

    def approved_fragments(db, plan, owner, refs=None):
        prefs = json.loads(plan["preferences_json"])
        scoped_call = refs is not None
        source = source_snapshot(db, plan["source_id"], owner, prefs["extraction_revision"])
        refs = refs or prefs["fragment_ids"]
        if not source['reviewed']:
            raise HTTPException(409, 'Bản trích nguồn chưa được xác nhận.')
        if len(set(refs)) != len(refs) or any(ref not in prefs["fragment_ids"] for ref in refs):
            raise HTTPException(422, "Phạm vi dùng nguồn nằm ngoài bản đã duyệt.")
        selected = [{"id": f["id"], "text": f["text"], "locator": f["locator"]} for f in source["fragments"] if f["id"] in refs]
        if any(f['locator'].get('unreadable_math') for f in selected):
            raise HTTPException(422,'Phạm vi có công thức Office Math chưa đọc được. Sửa bản trích hoặc bỏ đoạn đó khỏi phạm vi trước khi gọi AI.')
        if {f['id'] for f in selected} != set(refs):
            raise HTTPException(409, 'Phạm vi bài không khớp bản trích đã lưu; xem lại binding nguồn trước khi tiếp tục.')
        if scoped_call and not fits(selected):
            raise HTTPException(422, "Nguồn của bài vượt phạm vi model. Chia lại bài trong bản xem trước; chưa gọi AI hoặc giữ Coin.")
        return selected

    def plan_value(plan):
        return {"id": plan["id"], "source_id": plan["source_id"], "preferences": json.loads(plan["preferences_json"]), "outline": json.loads(plan["outline_json"]), "status": plan["status"]}

    @app.post("/api/plans")
    async def create_plan(body: Preferences, background: BackgroundTasks, request: Request, owner=Depends(user)):
        if len(body.fragment_ids) > MAX_AI_OUTLINE_FRAGMENTS:
            raise HTTPException(422, "Dùng /api/plans/from-source-sections để chia toàn bộ phạm vi theo bài; chưa gửi tài liệu dài vào một request AI.")
        identity = jobs.identity(request, "outline", body.model_dump(), owner=owner)
        previous = jobs.cached(owner, identity)
        if previous:
            return previous
        with database.connection() as db:
            source = source_snapshot(db, body.source_id, owner)
            if not source["reviewed"]:
                raise HTTPException(409, "Kiểm tra và xác nhận bản trích nguồn trước.")
            if body.expected_extraction_revision is not None and source["revision"] != body.expected_extraction_revision:
                raise HTTPException(409, "Bản trích đã đổi; tải lại trước khi tạo phác thảo.")
            if body.subject.lower() == 'unknown' or body.goal.lower() == 'unknown':
                raise HTTPException(409, "Xem lựa chọn/mặc định ở setup/clarify rồi xác nhận nhu cầu trước.")
            if len(set(body.fragment_ids)) != len(body.fragment_ids) or any(ref not in {f["id"] for f in source["fragments"]} for ref in body.fragment_ids):
                raise HTTPException(422, "Đoạn nguồn không thuộc phiên bản đã duyệt.")
            if any(ref not in {f['id'] for f in source['fragments']} for ref in body.excluded_fragment_ids):
                raise HTTPException(422, "Phần bỏ qua không thuộc bản trích này.")
            plan_id = new_id()
            prefs = {**body.model_dump(), "extraction_revision": source["revision"]}
            plan = {"source_id": body.source_id, "preferences_json": dump(prefs)}
            fragments = approved_fragments(db, plan, owner)
            if not fits(fragments):
                raise HTTPException(422, "Phạm vi dài: tạo lộ trình theo phần nguồn rồi sinh từng bài để không cắt nội dung.")

        def prepare(db):
            db.execute("INSERT INTO plans VALUES (?,?,?,?,?,?,?,?)", (plan_id, owner, body.source_id, dump(prefs), dump({"version": 1}), "generating", now(), None))

        async def work(job_id):
            try:
                semantic_prefs = {k: v for k, v in prefs.items() if k not in {"source_id", "fragment_ids", "extraction_revision"}}
                outline = await generate_checked(Outline, "Tạo phác thảo 1–3 bài, chưa tạo bài chi tiết hoặc câu hỏi. Đầu ra chỉ có title và units; mỗi unit chỉ có title, objective, source_refs. Không chép trường cấu hình vào đầu ra. Tuân thủ môn, mục tiêu và ngôn ngữ người học đã xác nhận: " + dump(semantic_prefs), fragments)
                with database.connection(write=True) as db:
                    jobs.check(db, job_id)
                    db.execute("UPDATE plans SET outline_json=?,status='preview' WHERE id=?", (dump({**outline, "version": 1}), plan_id))
                    result = {"plan_id": plan_id}
                    jobs.finish(db, job_id, result)
                return result
            except Exception:
                with database.connection(write=True) as db:
                    db.execute("UPDATE plans SET status='failed' WHERE id=?", (plan_id,))
                raise
        return new_job(owner, "outline", {"plan_id": plan_id,"source_id":body.source_id}, background, work, identity, prepare)

    @app.get("/api/plans/{plan_id}")
    def get_plan(plan_id: str, owner=Depends(user)):
        with database.connection() as db:
            return plan_value(owned(db, "plans", plan_id, owner))

    @app.get('/api/plans/{plan_id}/mode-previews')
    def mode_previews(plan_id: str, owner=Depends(user)):
        with database.connection() as db:
            value = plan_value(owned(db, 'plans', plan_id, owner))
            if value['status'] not in {'preview', 'approved'}:
                raise HTTPException(409, 'Phác thảo chưa sẵn sàng để duyệt.')
            return preview_modes(value['outline'], value['preferences'])

    @app.put("/api/plans/{plan_id}")
    def edit_plan(plan_id: str, body: PlanEdit, owner=Depends(user)):
        from .models import validate_refs
        with database.connection(write=True) as db:
            plan = owned(db, "plans", plan_id, owner)
            previous = json.loads(plan["outline_json"])
            if plan["status"] != "preview" or previous["version"] != body.expected_version:
                raise HTTPException(409, "Phác thảo đã đổi hoặc được duyệt; không ghi đè.")
            try:
                validate_refs(body.outline, {f["id"] for f in approved_fragments(db, plan, owner)})
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            if previous.get('method') in {'source_sections_not_ai', 'ai_blueprint'}:
                expected = set(json.loads(plan['preferences_json'])['fragment_ids'])
                assigned = {r for unit in body.outline.units for r in unit.source_refs}
                if assigned != expected:
                    raise HTTPException(422, 'Còn đoạn đã chọn chưa được phân bổ; phân bổ vào bài khác hoặc quay lại chọn phạm vi. Chưa bỏ nguồn âm thầm.')
            by_id = {f['id']:f for f in approved_fragments(db,plan,owner)}
            if any(not fits([by_id[r] for r in unit.source_refs]) for unit in body.outline.units):
                raise HTTPException(422, 'Một bài chứa quá nhiều chữ; giữ thành các bài nhỏ để AI đọc đủ nguồn.')
            db.execute("UPDATE plans SET outline_json=? WHERE id=?", (dump({**body.outline.model_dump(), **({"method": previous["method"]} if previous.get("method") else {}), "version": previous["version"] + 1}), plan_id))
            return plan_value(owned(db, "plans", plan_id, owner))

    @app.post("/api/plans/{plan_id}/approve")
    def approve(plan_id: str, body: Version, owner=Depends(user)):
        with database.connection(write=True) as db:
            plan = owned(db, "plans", plan_id, owner)
            prior = db.execute("SELECT r.course_id FROM course_revisions r JOIN courses c ON c.id=r.course_id WHERE r.plan_id=? AND c.owner_id=? LIMIT 1", (plan_id, owner)).fetchone()
            if prior:
                require_active(db,'course',prior['course_id'])
                return {"course_id": prior["course_id"]}
            outline = json.loads(plan["outline_json"])
            if plan["status"] != "preview" or outline["version"] != body.expected_revision:
                raise HTTPException(409, "Duyệt đúng phiên bản phác thảo đang xem.")
            prefs = json.loads(plan["preferences_json"])
            course_id = new_id()
            content = {"title": outline["title"], "unlock_policy": prefs["unlock_policy"], "preferences": prefs, "units": [{**unit, "id": f"unit-{i+1}", "data": None} for i, unit in enumerate(outline["units"])]}
            db.execute("UPDATE plans SET status='approved',approved_at=? WHERE id=?", (now(), plan_id))
            db.execute("INSERT INTO courses VALUES (?,?,?,?)", (course_id, owner, 1, now()))
            db.execute("INSERT INTO course_revisions VALUES (?,?,?,?,?)", (course_id, 1, plan_id, dump(content), now()))
            return {"course_id": course_id}

    @app.get("/api/courses")
    def courses(owner=Depends(user)):
        with database.connection() as db:
            return [reader_course(course_snapshot(db, course_id, owner)) for course_id in community.ids(db, owner)]

    @app.get("/api/courses/{course_id}")
    def get_course(course_id: str, owner=Depends(user)):
        with database.connection() as db:
            return reader_course(course_snapshot(db, course_id, owner))

    @app.get("/api/courses/{course_id}/editor")
    def course_editor(course_id: str, owner=Depends(user)):
        with database.connection() as db:
            owned(db, "courses", course_id, owner)
            if active_exam(db, owner, course_id):
                raise HTTPException(403, "Nộp hoặc hủy lượt kiểm tra trước khi mở đáp án ở bộ sửa.")
            return course_snapshot(db, course_id, owner)

    @app.get('/api/courses/{course_id}/source-fragments')
    def course_sources(course_id: str, unit_id: str | None = None, owner=Depends(user)):
        with database.connection() as db:
            course = course_snapshot(db, course_id, owner)
            values = {}
            for unit in course['content']['units']:
                if unit_id and unit['id'] != unit_id: continue
                if course['access_role'] != 'creator' and (not unit['unlocked'] or not unit.get('data')): continue
                plan = course_plan(db, course, owner, unit)
                for fragment in approved_fragments(db, plan, course['creator_id'], unit['source_refs']):
                    values[fragment['id']] = fragment
            return list(values.values())

    @app.get('/api/courses/{course_id}/chapter-context')
    def chapter_context(course_id: str, unit_id: str, owner=Depends(user)):
        with database.connection() as db:
            owned(db, 'courses', course_id, owner)
            course = course_snapshot(db, course_id, owner)
            unit = next((u for u in course['content']['units'] if u['id'] == unit_id), None)
            if not unit:raise HTTPException(404, 'Không có bài trong khóa này.')
            plan = course_plan(db, course, owner, unit)
            fragments = approved_fragments(db, plan, owner)
            binding = chapters.binding(plan, owner, fragments)
        # Progress only: this endpoint never leaks the private chapter analysis
        # or answer-bearing notes into a practice/exam screen.
        return chapters.describe(binding)

    def commit_course(db, course, owner, content, plan_id=None):
        current = owned(db, "courses", course["id"], owner)
        if current["active_revision"] != course["revision"]:
            raise HTTPException(409, "Khóa học đã có phiên bản mới; đề xuất cũ được giữ để xem lại, chưa áp dụng.")
        from .models import validate_refs
        for unit in content['units']:
            plan = owned(db, 'plans', unit.get('source_plan_id', plan_id or course['plan_id']), owner)
            if plan['status'] != 'approved':
                raise HTTPException(409, 'Bài tham chiếu phác thảo nguồn chưa được duyệt.')
            fragments = approved_fragments(db, plan, owner, unit['source_refs'])
            if unit.get('data'):
                try:
                    validate_refs(unit['data'], {f['id'] for f in fragments})
                except ValueError as exc:
                    raise HTTPException(422, 'Nội dung bài không khớp nguồn riêng đã duyệt.') from exc
        revision = course["revision"] + 1
        db.execute("INSERT INTO course_revisions VALUES (?,?,?,?,?)", (course["id"], revision, plan_id or course["plan_id"], dump(content), now()))
        db.execute("UPDATE courses SET active_revision=? WHERE id=?", (revision, course["id"]))
        return {"course_id": course["id"], "revision": revision}

    @app.post("/api/courses/{course_id}/generate")
    async def generate_unit(course_id: str, body: GenerateUnit, background: BackgroundTasks, request: Request, owner=Depends(user)):
        with database.connection() as db:
            owned(db, 'courses', course_id, owner)
        payload = {**body.model_dump(), "course_id": course_id}
        identity = jobs.identity(request, "lesson", payload, owner=owner)
        previous = jobs.cached(owner, identity)
        if previous:
            return previous
        with database.connection() as db:
            course = course_snapshot(db, course_id, owner)
            if course["revision"] != body.expected_revision:
                raise HTTPException(409, "Khóa học đã đổi; tải lại trước khi tạo.")
            unit = unit_from(course, body.unit_id)
            if unit["data"]:
                raise HTTPException(409, "Bài đã có nội dung. Dùng sửa có phạm vi và xem trước.")
            plan = course_plan(db, course, owner, unit)
            if plan["status"] != "approved":
                raise HTTPException(409, "Chưa duyệt lộ trình.")
            fragments = approved_fragments(db, plan, course["creator_id"], unit["source_refs"])
            chapter_fragments = approved_fragments(db, plan, owner)
            chapter_binding = chapters.binding(plan, owner, chapter_fragments)
            prefs = json.loads(plan["preferences_json"])
            evidence_scope = None
            reading = None
            saved_questions = {}
            question_rejections = {}
            stage_providers = {}
            question_focus_plan, stage_focus = None, {}
            if body.resume_job_id:
                previous = owned(db, "jobs", body.resume_job_id, owner)
                previous_payload = json.loads(previous["payload_json"])
                if previous["task"] != "lesson" or previous["status"] not in {"failed", "cancelled"} or previous_payload.get("course_id") != course_id or previous_payload.get("unit_id") != body.unit_id or previous_payload.get("expected_revision") != body.expected_revision:
                    raise HTTPException(409, "Phần đã tạo không khớp bài hoặc phiên bản đang xem.")
                previous_partial = json.loads(previous["partial_json"])
                evidence_scope = previous_partial.get('evidence_scope')
                if evidence_scope:
                    fragments = chapter_evidence.validate(evidence_scope, chapter_fragments, unit, chapter_binding['id'])
                reading = previous_partial.get("reading")
                question_focus_plan = previous_partial.get('question_focus_plan')
                stage_focus = previous_partial.get('stage_focus', {})
                if question_focus_plan:
                    question_focus.validate(question_focus_plan, chapter_binding['id'], evidence_scope, unit, prefs, reading)
                question_focus.validate_requests(question_focus_plan, stage_focus)
                # A null draft is not a usable question. An explicit retry may
                # ask once again for it; already valid items remain reused.
                saved_questions = {k: v for k, v in previous_partial.get("questions", {}).items() if v.get("question") is not None}
                previous_provider = previous_payload.get('_provider', {'provider': 'legacy_unrecorded'})
                stage_providers = previous_partial.get('stage_providers', {})
                question_rejections = previous_partial.get('question_rejections', {})
                if reading:
                    stage_providers.setdefault('reading', previous_provider)
                for key in saved_questions:
                    stage_providers.setdefault(key, previous_provider)
                for key in list(saved_questions):
                    try:
                        verify_mcq_options(saved_questions[key]['question'])
                        verify_ordering(saved_questions[key]['question'], fragments)
                        subnet_reasoning.check_question(saved_questions[key]['question'])
                    except ValueError:
                        # A partial generated before this validator must not
                        # bypass it when an explicit retry reuses saved stages.
                        del saved_questions[key]
                if not reading and not previous_partial.get('chapter_context'):
                    raise HTTPException(409, "Job này chưa có phần bài học hợp lệ để tiếp tục.")
                from .models import validate_refs
                try:
                    allowed={f['id'] for f in chapter_fragments}
                    if reading:validate_refs(reading,allowed)
                    for value in saved_questions.values():validate_refs(value,allowed)
                except ValueError as exc:
                    raise HTTPException(409,'Phần đã lưu có trích dẫn ngoài chương đã duyệt; chưa đọc chương hoặc gọi tạo tiếp.') from exc

        async def work(job_id):
            nonlocal fragments, evidence_scope, question_focus_plan
            chapter_before = chapters.describe(chapter_binding)
            chapter_progress = chapter_before
            chapter_total = chapter_before['total_stages']
            planned = chapter_total + 1 + (prefs.get('question_count') or len(prefs.get('question_types') or QUESTION_DRAFTS))
            reused = chapter_before['saved_stages'] + int(bool(reading)) + len(saved_questions)
            def checkpoint_chapter(progress):
                nonlocal chapter_progress
                chapter_progress = progress
                with database.connection(write=True) as db:
                    jobs.check(db, job_id)
                    db.execute('UPDATE jobs SET partial_json=?,updated_at=? WHERE id=?',
                               (dump({'chapter_context': progress, 'evidence_scope': evidence_scope, 'reading': reading, 'questions': saved_questions,
                                      'stage_providers': stage_providers, 'question_rejections': question_rejections,
                                      'question_focus_plan': question_focus_plan, 'stage_focus': stage_focus}), now(), job_id))
                    job_progress.chapter(db, job_id, progress)
                    jobs.saved_stages(db, job_id, planned, progress['saved_stages'] + int(bool(reading)) + len(saved_questions), reused)
            chapter_progress, chapter_nodes = await chapters.prepare(chapter_binding, job_id, prefs, identity['provenance'], checkpoint_chapter)
            if not chapter_progress['complete']:
                result = {'course_id': course_id, 'unit_id': body.unit_id, 'revision': course['revision'],
                          'continuation_required': True, 'chapter_context': chapter_progress,
                          'message': 'Đã lưu phần đọc chương. Bấm tiếp tục để đọc/tổng hợp phần còn lại trước khi tạo câu hỏi.'}
                with database.connection(write=True) as db:
                    jobs.finish(db, job_id, result)
                return result
            fragments, evidence_scope = chapter_evidence.select(chapter_fragments, unit, prefs,
                chapters.summary(chapter_binding, chapter_nodes), chapter_binding['id'], evidence_scope)
            from .models import validate_refs
            if reading:validate_refs(reading,{f['id'] for f in fragments})
            for drafted in saved_questions.values():validate_refs(drafted,{f['id'] for f in fragments})
            unit['source_refs'] = evidence_scope['input_source_refs']
            # Pin the evidence before the first model request too. A malformed
            # reading is not usable content, but its source scope must survive
            # a disconnect/schema failure so an explicit retry cannot re-rank it.
            checkpoint_chapter(chapter_progress)
            instruction = (lesson_instruction(prefs,unit) + chapters.instruction(chapter_binding, chapter_nodes, evidence_scope['focus_source_refs'])
                           + chapter_evidence.instruction(evidence_scope))
            card_target = prefs.get('card_count') or 2
            partial_reading = reading or await generate_checked(LessonReading, instruction + f"\nChỉ tạo phần đọc: 3 mục lý thuyết ngắn có ví dụ trong nội dung, đúng {card_target} flashcard, mindmap 3 ý. Mỗi text/back tối đa 100 từ. Viết ngôn ngữ đã chọn; language=source thì giữ ngôn ngữ nguồn. Notes là chú thích do người học cung cấp, không thay nguyên văn nguồn. Giữ terms_to_keep và từ đang học. Chưa tạo câu hỏi. Chỉ có title, sections, cards, mindmap theo schema. "
                "Mỗi phần tử sections VÀ mỗi phần tử mindmap đều có đủ title, text, source_refs. Mỗi phần tử cards có đủ front, back, source_refs. source_refs là danh sách không rỗng, chọn đúng nguồn hỗ trợ riêng nội dung đó; mindmap không được bỏ source_refs hoặc dồn nguồn lên cấp ngoài. Tự kiểm đủ các trường trước khi xuất JSON; không đoán nguồn khi thiếu căn cứ.", fragments)
            stage_providers.setdefault('reading', identity['provenance'])
            if prefs.get('card_count') and len(partial_reading['cards']) != prefs['card_count']:
                raise ValueError('Số thẻ AI trả chưa khớp số đã duyệt; chưa áp dụng phần này.')
            validate_language(partial_reading, prefs)
            def save_partial():
                with database.connection(write=True) as db:
                    jobs.check(db, job_id)
                    db.execute("UPDATE jobs SET partial_json=?,updated_at=? WHERE id=?", (dump({"chapter_context": chapter_progress, "evidence_scope": evidence_scope, "reading": partial_reading, "questions": saved_questions, 'stage_providers': stage_providers, 'question_rejections':question_rejections,
                        'question_focus_plan': question_focus_plan, 'stage_focus': stage_focus}), now(), job_id))
                    jobs.saved_stages(db, job_id, planned, chapter_total + 1 + len(saved_questions), reused)
            save_partial()
            question_focus_plan = question_focus.prepare(chapter_binding['id'], evidence_scope, unit, prefs, partial_reading,
                chapters.summary(chapter_binding, chapter_nodes), fragments, question_focus_plan)
            save_partial()
            stages = question_stages(prefs)
            count = len(stages)
            for key, kind in stages:
                schema = QUESTION_DRAFTS[kind]
                if key in saved_questions:
                    continue
                question_rejections.pop(key, None)
                if kind == 'ordering' and not explicit_sequence(fragments):
                    saved_questions[key] = {'question': None, 'reason': 'Nguồn của bài chưa có các bước đánh số theo trình tự rõ. Không biến danh sách khái niệm thành câu sắp xếp.'}
                    save_partial()
                    continue
                question_focus.record_request(question_focus_plan, stage_focus, key, job_id)
                save_partial()
                prompt = question_prompt(instruction, kind, unit["objective"], [q["question"] for q in saved_questions.values() if q.get("question")]) + question_focus.instruction(question_focus_plan, key)
                try:
                    drafted = await generate_checked(schema, prompt, fragments)
                    reject_duplicate_prompt(drafted,[q['question'] for q in saved_questions.values() if q.get('question')])
                except QuestionRejected as exc:
                    # A proved candidate failure concerns this question only.
                    # Preserve the reason; never invent a key or call the model
                    # again automatically. Connectivity/ACL/JSON errors still
                    # propagate, so this cannot hide a broken provider.
                    drafted = {'question':None, 'reason':str(exc)}
                    question_rejections[key] = exc.details
                validate_language(drafted, prefs)
                if drafted['question']:
                    verify_ordering(drafted['question'], fragments)
                    if prefs.get('difficulty'):
                        drafted['question'].update(difficulty=prefs['difficulty'], difficulty_basis='creator_request_not_measured')
                saved_questions[key] = drafted
                stage_providers[key] = identity['provenance']
                save_partial()
            questions = [q["question"] for q in saved_questions.values() if q["question"] is not None]
            for q in questions:
                verify_ordering(q, fragments)
            if not questions:
                raise ValueError("Chưa có câu hỏi sử dụng được cho mục tiêu/phạm vi của bài này. Bài đọc đã lưu; đối chiếu và sửa phạm vi hoặc thử lại có giới hạn. Lý do từng dạng còn trong job.partial.questions.")
            lesson = Lesson.model_validate({**partial_reading, "questions": questions}).model_dump()
            unit["data"] = lesson
            with database.connection(write=True) as db:
                jobs.check(db, job_id)
                unit['generation'] = {'job_id': job_id, 'provider': identity['provenance'], 'source_id': plan['source_id'], 'source_plan_id': plan['id'], 'extraction_revision': prefs['extraction_revision'], 'source_refs': unit['source_refs'], 'content_language': prefs['language'], 'generated_at': now()}
                unit['generation'].update(stage_providers=stage_providers, resumed_from_job_id=body.resume_job_id)
                unit['generation']['chapter_context'] = chapter_progress
                unit['generation']['evidence_scope'] = evidence_scope
                unit['generation'].update(question_focus_plan=question_focus_plan, stage_focus=stage_focus)
                unit['generation']['question_coverage'] = {
                    'requested_count': count, 'generated_count': len(questions), 'complete': len(questions) == count,
                    'requested_types': list(dict.fromkeys(kind for _,kind in stages)),
                    'generated_types': list(dict.fromkeys(q['kind'] for q in questions)),
                    'uncreated': [{'stage':key, 'kind':kind, 'reason':saved_questions[key]['reason'],
                                   'origin':question_rejections[key]['origin'] if key in question_rejections else 'backend_source_gate' if kind=='ordering' and not explicit_sequence(fragments) else 'model_declined',
                                   **({'code':question_rejections[key]['code']} if key in question_rejections else {})}
                                  for key,kind in stages if saved_questions[key]['question'] is None],
                }
                result = commit_course(db, course, owner, course["content"])
                jobs.finish(db, job_id, result)
                return result
        return new_job(owner, "lesson", payload, background, work, identity)

    @app.post("/api/courses/{course_id}/sessions")
    def start_session(course_id: str, body: PracticeRequest, request: Request, owner=Depends(user)):
        with database.connection(write=True) as db:
            course = course_snapshot(db, course_id, owner)
            request_key = request.headers.get("Idempotency-Key")
            digest = hashlib.sha256(json.dumps(body.model_dump(), sort_keys=True).encode()).hexdigest()
            if request_key:
                if len(request_key) > 128 or not request_key.strip():
                    raise HTTPException(422, "Idempotency-Key cần 1–128 ký tự.")
                previous = db.execute("SELECT digest,result_json FROM idempotency WHERE owner_id=? AND operation=? AND request_key=?", (owner, "session:" + course_id, request_key)).fetchone()
                if previous:
                    if previous["digest"] != digest:
                        raise HTTPException(409, "Khóa yêu cầu đã dùng cho phạm vi khác.")
                    return json.loads(previous["result_json"])
            if active_test(db, owner, course_id):
                raise HTTPException(409, "Tiếp tục/nộp hoặc hủy lượt kiểm tra đang mở trước khi bắt đầu lượt khác.")
            if course["revision"] != body.expected_revision:
                raise HTTPException(409, "Bắt đầu lượt theo phiên bản mới nhất.")
            unit_ids = body.unit_ids or ([body.unit_id] if body.unit_id else [])
            if not unit_ids or len(unit_ids) != len(set(unit_ids)) or body.question_types and (len(set(body.question_types)) != len(body.question_types) or not set(body.question_types) <= KINDS):
                raise HTTPException(422, "Chọn phạm vi và các dạng câu hợp lệ, không lặp.")
            units = [unit_from(course, unit_id, ready=True) for unit_id in unit_ids]
            items = [question_item(course_id, unit["id"], i, q) for unit in units for i, q in enumerate(unit["data"]["questions"])]
            bank_warnings = []
            for q in items:
                try:
                    verify_mcq_options(q)
                except ValueError as exc:
                    reason = str(exc)
                    db.execute("INSERT INTO question_review_flags VALUES (?,?,?,?,?) ON CONFLICT(course_id,question_revision_id) DO UPDATE SET state=excluded.state,reason=excluded.reason", (course_id, q['question_revision_id'], 'needs_review', reason, now()))
                    bank_warnings.append({'item_id': q['id'], 'reason': reason, 'state': 'needs_review'})
            for unit in units:
                ordering_items = [q for q in items if q['unit_id'] == unit['id'] and q['kind'] == 'ordering']
                if not ordering_items:
                    continue
                plan = course_plan(db, course, owner, unit)
                fragments = approved_fragments(db, plan, course['creator_id'], unit['source_refs'])
                for q in ordering_items:
                    try:
                        verify_ordering(q, fragments)
                    except ValueError as exc:
                        reason = str(exc)
                        db.execute("INSERT INTO question_review_flags VALUES (?,?,?,?,?) ON CONFLICT(course_id,question_revision_id) DO UPDATE SET state=excluded.state,reason=excluded.reason", (course_id, q['question_revision_id'], 'needs_review', reason, now()))
                        bank_warnings.append({'item_id': q['id'], 'reason': reason, 'state': 'needs_review'})
            blocked = {r[0] for r in db.execute("SELECT question_revision_id FROM question_review_flags WHERE course_id=? AND state='needs_review'", (course_id,))}
            items = [q for q in items if q["question_revision_id"] not in blocked]
            if body.question_types:
                items = [q for q in items if q["kind"] in body.question_types]
            if body.difficulty:
                items = [q for q in items if q.get("difficulty") == body.difficulty]
            if body.exercise == "weak":
                weak_ids = {v["question_revision_id"] for v in learning.weak(db, owner, course_id)}
                items = [q for q in items if q["question_revision_id"] in weak_ids]
                if not items:
                    return JSONResponse(status_code=409, content={'detail': "Chưa có câu sai phù hợp ở bản hiện tại. Bắt đầu một lượt luyện thông thường; không tạo phần yếu giả.", 'bank_warnings': bank_warnings})
            if not items or body.question_count and body.question_count > len(items):
                # Return normally so this diagnostic transaction retains review
                # flags even when every question in the bank was quarantined.
                return JSONResponse(status_code=422, content={'detail': "Bộ đã tạo chưa đủ câu đúng phạm vi/dạng/mức đã chọn. Không tự sinh thêm hoặc lặp câu để đủ số.", 'bank_warnings': bank_warnings})
            if body.question_count:
                items = items[:body.question_count]
            session_id = new_id()
            scope = {"unit_id": unit_ids[0] if len(unit_ids) == 1 else None, "unit_ids": unit_ids, "exercise": body.exercise, "question_types": body.question_types, "difficulty": body.difficulty, "bank_warnings": bank_warnings}
            db.execute("INSERT INTO study_sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (session_id, owner, course_id, course["revision"], body.mode, int(body.exercise == "test"), dump(scope), dump(items), "open", now(), None, None))
            learning.update_progress(db, owner, course_id, {"mode": "practice", "unit_id": items[0]["unit_id"], "session_id": session_id, "item_id": items[0]["id"], "expected_revision": course["revision"]})
            result = {"id": session_id, "revision": course["revision"], "mode": body.mode, "scope": scope, "exam": body.exercise == "test", "questions": [public_question(item) for item in items]}
            if request_key:
                db.execute("INSERT INTO idempotency VALUES (?,?,?,?,?,?)", (owner, "session:" + course_id, request_key, digest, dump(result), now()))
        return result

    @app.post("/api/sessions/{session_id}/answers")
    def answer(session_id: str, body: Answer, owner=Depends(user)):
        with database.connection(write=True) as db:
            session = owned(db, "study_sessions", session_id, owner)
            if not session["exam"] and active_test(db, owner, session["course_id"]):
                raise HTTPException(403, "Phản hồi luyện mở sau lượt kiểm tra đang diễn ra.")
            prior = db.execute("SELECT answer_json,result_json FROM answers WHERE session_id=? AND item_id=?", (session_id, body.item_id)).fetchone()
            if prior:
                if json.loads(prior["answer_json"]) != body.answer and not (session["exam"] and session["status"] == "open"):
                    raise HTTPException(409, "Câu đã chấm; bắt đầu lượt mới để luyện lại.")
                if json.loads(prior["answer_json"]) == body.answer:
                    return {"accepted": True, "item_id": body.item_id} if session["exam"] and session["status"] != "completed" else json.loads(prior["result_json"])
            if session["status"] != "open":
                raise HTTPException(409, "Lượt đã kết thúc.")
            question = next((q for q in json.loads(session["items_json"]) if q["id"] == body.item_id), None)
            if not question:
                raise HTTPException(422, "Câu không thuộc lượt này.")
            try:
                result = grade_answer(question, body.answer)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            assisted = db.execute("SELECT 1 FROM assistance_events WHERE session_id=? AND item_id=?", (session_id, body.item_id)).fetchone() is not None
            db.execute("INSERT INTO answers VALUES (?,?,?,?,?,?) ON CONFLICT(session_id,item_id) DO UPDATE SET answer_json=excluded.answer_json,result_json=excluded.result_json,assisted=excluded.assisted,answered_at=excluded.answered_at", (session_id, body.item_id, dump(body.answer), dump(result), int(assisted), now()))
            db.execute("DELETE FROM session_drafts WHERE session_id=? AND item_id=?", (session_id, body.item_id))
            learning.update_progress(db, owner, session["course_id"], {"mode": "practice", "unit_id": question.get("unit_id") or body.item_id.rsplit(":q", 1)[0], "session_id": session_id, "item_id": body.item_id, "expected_revision": session["course_revision"]})
            return {"accepted": True, "item_id": body.item_id} if session["exam"] else result

    @app.put("/api/sessions/{session_id}/draft")
    def save_answer_draft(session_id: str, body: AnswerDraft, owner=Depends(user)):
        with database.connection(write=True) as db:
            session = owned(db, "study_sessions", session_id, owner)
            if session["status"] != "open":
                raise HTTPException(409, "Lượt không còn mở để lưu nháp.")
            item = next((q for q in json.loads(session["items_json"]) if q["id"] == body.item_id), None)
            if not item or len(dump(body.answer)) > 6000:
                raise HTTPException(422, "Câu/nháp không hợp lệ.")
            if not session["exam"] and db.execute("SELECT 1 FROM answers WHERE session_id=? AND item_id=?", (session_id, body.item_id)).fetchone():
                raise HTTPException(409, "Câu đã chấm; không thay bằng nháp mới.")
            previous = db.execute("SELECT version FROM session_drafts WHERE session_id=? AND item_id=?", (session_id, body.item_id)).fetchone()
            version = previous[0] if previous else 0
            if body.expected_version != version:
                raise HTTPException(409, "Nháp đã đổi ở phiên khác.")
            db.execute("INSERT INTO session_drafts VALUES (?,?,?,?,?) ON CONFLICT(session_id,item_id) DO UPDATE SET answer_json=excluded.answer_json,version=excluded.version,updated_at=excluded.updated_at", (session_id, body.item_id, dump(body.answer), version + 1, now()))
            learning.update_progress(db, owner, session["course_id"], {"mode": "practice", "unit_id": item.get("unit_id") or body.item_id.rsplit(":q", 1)[0], "session_id": session_id, "item_id": body.item_id, "expected_revision": session["course_revision"]})
            return {"item_id": body.item_id, "version": version + 1, "graded": False}

    @app.post("/api/sessions/{session_id}/complete")
    def complete(session_id: str, owner=Depends(user)):
        with database.connection(write=True) as db:
            session = owned(db, "study_sessions", session_id, owner)
            if session["result_json"]:
                return json.loads(session["result_json"])
            if session["status"] != "open":
                raise HTTPException(409, "Lượt không còn mở để nộp.")
            answers = db.execute("SELECT result_json FROM answers WHERE session_id=?", (session_id,)).fetchall()
            if len(answers) != len(json.loads(session["items_json"])):
                raise HTTPException(409, "Gửi đủ câu trả lời trước khi hoàn thành.")
            results = [json.loads(a["result_json"]) for a in answers]
            assisted_count = db.execute("SELECT count(*) FROM answers WHERE session_id=? AND assisted=1", (session_id,)).fetchone()[0]
            result = {"score": sum(r["correct"] is True for r in results), "fixed_total": sum(r["correct"] is not None for r in results), "self_review_count": sum(r["correct"] is None for r in results), "course_revision": session["course_revision"], "session_id": session_id, "assisted_count": assisted_count, "assessment": "self_study_not_proctored"}
            db.execute("UPDATE study_sessions SET status='completed',completed_at=?,result_json=? WHERE id=?", (now(), dump(result), session_id))
            unit_ids = {q.get("unit_id") or q["id"].rsplit(":q", 1)[0] for q in json.loads(session["items_json"])}
            for unit_id in unit_ids:
                db.execute("INSERT OR IGNORE INTO unit_completions VALUES (?,?,?,?,?,?)", (owner, session["course_id"], session["course_revision"], unit_id, session_id, now()))
            result['rewards'] = activity.complete(db, owner, session)
            db.execute('UPDATE study_sessions SET result_json=? WHERE id=?', (dump(result), session_id))
            return result

    @app.get("/api/courses/{course_id}/history")
    def history(course_id: str, owner=Depends(user)):
        with database.connection() as db:
            historical=db.execute('SELECT 1 FROM study_sessions WHERE course_id=? AND owner_id=? LIMIT 1',(course_id,owner)).fetchone()
            if not historical and deleted(db,'course',course_id):
                creator=db.execute('SELECT 1 FROM courses WHERE id=? AND owner_id=?',(course_id,owner)).fetchone()
                if not creator:raise HTTPException(404,'Không có lịch sử riêng của khóa này.')
            elif not historical:course_snapshot(db, course_id, owner)
            return [{"id": r["id"], "revision": r["course_revision"], "status": r["status"], "result": json.loads(r["result_json"]) if r["result_json"] else None, 'reference_warnings': reference_warnings(db, r), "created_at": r["created_at"]} for r in db.execute("SELECT * FROM study_sessions WHERE owner_id=? AND course_id=? ORDER BY created_at DESC", (owner, course_id))]

    @app.get("/api/sessions/{session_id}")
    def session_state(session_id: str, owner=Depends(user)):
        with database.connection() as db:
            session = owned(db, "study_sessions", session_id, owner)
            withheld = active_test(db, owner, session["course_id"])
            results = {r["item_id"]: {"answer": json.loads(r["answer_json"]), "feedback": json.loads(r["result_json"]) if not withheld and (not session["exam"] or session["status"] == "completed") else None, "assisted": bool(r["assisted"])} for r in db.execute("SELECT * FROM answers WHERE session_id=?", (session_id,))}
            drafts = {r["item_id"]: {"answer": json.loads(r["answer_json"]), "version": r["version"]} for r in db.execute("SELECT * FROM session_drafts WHERE session_id=?", (session_id,))}
            warnings = reference_warnings(db, session)
        return {"id": session_id, "revision": session["course_revision"], "scope": json.loads(session["scope_json"]), "mode": session["mode"], "exam": bool(session["exam"]), "status": session["status"], "questions": [public_question(q) for q in json.loads(session["items_json"])], "answers": results, "drafts": drafts, "feedback_deferred": withheld, 'reference_warnings': warnings, "result": json.loads(session["result_json"]) if session["result_json"] and not withheld else None}

    @app.post("/api/sessions/{session_id}/cancel")
    def cancel_session(session_id: str, owner=Depends(user)):
        with database.connection(write=True) as db:
            session = owned(db, "study_sessions", session_id, owner)
            if session["status"] == "completed":
                raise HTTPException(409, "Lượt đã nộp; lịch sử được giữ nguyên.")
            db.execute("UPDATE study_sessions SET status='cancelled' WHERE id=?", (session_id,))
            return {"id": session_id, "status": "cancelled"}

    @app.post("/api/sessions/{session_id}/items/{item_id}/solution")
    def saved_solution(session_id: str, item_id: str, owner=Depends(user)):
        with database.connection(write=True) as db:
            session = owned(db, "study_sessions", session_id, owner)
            if active_test(db, owner, session["course_id"]):
                raise HTTPException(403, "Lời giải mở sau khi nộp hoặc hủy lượt kiểm tra.")
            item = next((q for q in json.loads(session["items_json"]) if q["id"] == item_id), None)
            if not item:
                raise HTTPException(404, "Câu không thuộc lượt này.")
            if session["status"] == "open":
                db.execute("INSERT OR IGNORE INTO assistance_events VALUES (?,?,?,?)", (session_id, item_id, "saved_solution", now()))
                db.execute("UPDATE answers SET assisted=1 WHERE session_id=? AND item_id=?", (session_id, item_id))
            return {"reference": item["answer"], "explanation": item["explanation"], "rubric": item.get("rubric", []), "source_refs": item["source_refs"], "assisted": True, "ai_called": False}

    @app.post("/api/courses/{course_id}/question-reports")
    def report_question(course_id: str, body: QuestionReport, owner=Depends(user)):
        with database.connection(write=True) as db:
            owned(db, "courses", course_id, owner)
            course = course_snapshot(db, course_id, owner)
            if course["revision"] != body.expected_revision:
                raise HTTPException(409, "Báo đúng phiên bản đang xem.")
            unit = unit_from(course, body.unit_id, ready=True)
            item = next((q for i, raw in enumerate(unit["data"]["questions"]) if (q := question_item(course_id, unit["id"], i, raw))["id"] == body.item_id), None)
            if not item:
                raise HTTPException(404, "Không có câu này trong bài.")
            db.execute("INSERT INTO question_review_flags VALUES (?,?,?,?,?) ON CONFLICT(course_id,question_revision_id) DO UPDATE SET state=excluded.state,reason=excluded.reason", (course_id, item["question_revision_id"], "needs_review", body.reason, now()))
            return {"question_revision_id": item["question_revision_id"], "state": "needs_review", "old_attempts_preserved": True}

    @app.post("/api/courses/{course_id}/proposals")
    async def propose(course_id: str, body: Correction, background: BackgroundTasks, request: Request, owner=Depends(user)):
        with database.connection() as db:
            owned(db, 'courses', course_id, owner)
        from .models import validate_refs
        # Omit the new optional None to keep old idempotency payloads stable.
        payload = {**body.model_dump(exclude={'resume_job_id'} if body.resume_job_id is None else set()), "course_id": course_id}
        identity = None
        if body.replacement is None:
            identity = jobs.identity(request, "correction", payload, owner=owner)
            previous = jobs.cached(owner, identity)
            if previous:
                return previous
        with database.connection() as db:
            course = course_snapshot(db, course_id, owner)
            if active_exam(db, owner, course_id) or (body.replacement is None and rooms.active(db, owner, course_id)):
                raise HTTPException(403, "Nộp hoặc hủy kiểm tra trước khi mở bộ sửa nội dung.")
            if course["revision"] != body.expected_revision:
                raise HTTPException(409, "Chọn lại phạm vi trên phiên bản mới.")
            unit = unit_from(course, body.unit_id, ready=True)
            plan = course_plan(db, course, owner, unit)
            fragments = approved_fragments(db, plan, course["creator_id"], unit["source_refs"])
            prefs = json.loads(plan['preferences_json'])
            if body.replacement is None:
                chapter_fragments = approved_fragments(db, plan, owner)
                chapter_binding = chapters.binding(plan, owner, chapter_fragments)
        schema = {"lesson": Lesson, "question": Question, "card": Card}[body.target]
        collection = {"question": "questions", "card": "cards"}.get(body.target)
        if collection and body.index >= len(unit["data"][collection]):
            raise HTTPException(422, "Mục chọn không có trong bài.")
        before = unit["data"][collection][body.index] if collection else unit["data"]

        def validate_replacement(replacement):
            try:
                replacement = schema.model_validate(replacement).model_dump()
                validate_refs(replacement, {f["id"] for f in fragments})
                if body.target == 'question':
                    verify_ordering(replacement, fragments)
                    subnet_reasoning.check_question(replacement)
                elif body.target == 'lesson':
                    for q in replacement['questions']:
                        verify_ordering(q, fragments)
                        subnet_reasoning.check_question(q)
            except ValueError as exc:
                raise HTTPException(422, "Bản sửa chưa đúng cấu trúc hoặc phạm vi nguồn: " + str(exc)[:300]) from exc
            return replacement

        def save_proposal(replacement, job_id=None, provenance=None):
            replacement = validate_replacement(replacement)
            content = copy.deepcopy(course["content"])
            target = next(u for u in content["units"] if u["id"] == body.unit_id)
            if collection:
                target["data"][collection][body.index] = replacement
            else:
                target["data"] = replacement
            if provenance:
                target.setdefault('generation', {}).setdefault('correction_history', []).append(provenance)
            proposal_id = new_id()
            with database.connection(write=True) as db:
                if job_id:
                    jobs.check(db, job_id)
                db.execute("INSERT INTO revision_proposals VALUES (?,?,?,?,?,?,?,?,?)", (proposal_id, owner, course_id, course["revision"], dump({"unit_id": body.unit_id, "target": body.target, "index": body.index}), body.request, dump({"before": before, "after": replacement, "content": content}), "preview", now()))
                if job_id:
                    jobs.finish(db, job_id, {"proposal_id": proposal_id})
            return {"proposal_id": proposal_id}

        if body.replacement is not None:
            return save_proposal(body.replacement)

        scope = correction_context.binding(course, unit, plan, prefs, fragments, before, body, chapter_binding['id'])
        replacement, replacement_provider, replacement_input_strategy = None, None, None
        if body.resume_job_id:
            with database.connection() as db:
                previous = owned(db, 'jobs', body.resume_job_id, owner)
                partial = correction_context.check_resume(previous, payload, scope)
            replacement = partial.get('replacement')
            replacement_provider = partial.get('replacement_provider')
            if replacement is not None:
                replacement_input_strategy = partial.get('replacement_input_strategy') or correction_prompt.LEGACY_STRATEGY
                replacement = validate_replacement(replacement)
                validate_language(replacement, prefs)
                if body.target == 'question' and replacement['kind'] != before['kind']:
                    raise HTTPException(409, 'Checkpoint sửa một câu không khớp dạng câu đã chọn.')

        async def work(job_id):
            nonlocal replacement, replacement_provider, replacement_input_strategy
            chapter_progress = chapters.describe(chapter_binding)
            total = chapter_progress['total_stages'] + 1
            reused = chapter_progress['saved_stages'] + int(replacement is not None)
            rejection, decline = None, None
            def checkpoint():
                with database.connection(write=True) as db:
                    jobs.check(db, job_id)
                    db.execute('UPDATE jobs SET partial_json=?,updated_at=? WHERE id=?', (dump({
                        'correction_scope': scope, 'chapter_context': chapter_progress,
                        'replacement': replacement, 'replacement_provider': replacement_provider,
                        'replacement_input_strategy': replacement_input_strategy,
                        'replacement_sha256': correction_context.digest(replacement) if replacement is not None else None,
                        'candidate_rejection': rejection, 'decline_reason': decline}), now(), job_id))
                    job_progress.chapter(db, job_id, chapter_progress)
                    jobs.saved_stages(db, job_id, total, chapter_progress['saved_stages'] + int(replacement is not None), reused)
            def checkpoint_chapter(progress):
                nonlocal chapter_progress
                chapter_progress = progress
                checkpoint()
            chapter_progress, chapter_nodes = await chapters.prepare(chapter_binding, job_id, prefs, identity['provenance'], checkpoint_chapter)
            if not chapter_progress['complete']:
                result = {'course_id': course_id, 'unit_id': body.unit_id, 'base_revision': course['revision'],
                          'continuation_required': True, 'chapter_context': chapter_progress,
                          'message': 'Đã lưu phần đọc chương. Tiếp tục để đọc đủ trước khi đề xuất sửa; bài đang học giữ nguyên.'}
                with database.connection(write=True) as db: jobs.finish(db, job_id, result)
                return result
            chapter_instruction = chapters.instruction(chapter_binding, chapter_nodes, unit['source_refs'])
            if replacement is None:
                try:
                    if body.target == 'question':
                        kind = before['kind']
                        if kind not in QUESTION_DRAFTS: raise ValueError('Dạng câu cũ chưa hợp lệ; chỉnh tay trước khi nhờ AI sửa.')
                        instruction = correction_prompt.question_prompt(prefs, unit, before, body.request, chapter_instruction)
                        drafted = await generate_checked(QUESTION_DRAFTS[kind], instruction, fragments)
                        if drafted['question'] is None:
                            decline = drafted['reason']; checkpoint()
                            raise ProviderError('CORRECTION_SOURCE_INSUFFICIENT', 'AI chưa tạo được bản sửa có căn cứ; lý do đã lưu, chưa thay câu hoặc gọi lại tự động.')
                        candidate = drafted['question']
                        if candidate['kind'] != kind: raise ValueError('Bản sửa phải giữ dạng câu đã chọn; đổi dạng dùng chỉnh tay rõ ràng.')
                        if candidate['prompt'] != before['prompt']:
                            reject_duplicate_prompt(drafted, [q for i,q in enumerate(unit['data']['questions']) if i != body.index])
                        replacement = validate_replacement(correction_prompt.with_creator_metadata(candidate, before))
                        replacement_input_strategy = correction_prompt.INPUT_STRATEGY
                    else:
                        instruction = ("Sửa đúng phần được chọn; chưa áp dụng vào khóa học. Yêu cầu sửa hiện tại có ưu tiên cao hơn cách diễn đạt của bản cũ. Không mở rộng đề hoặc thêm ý mà yêu cầu sửa không chọn. Giữ nguyên các phần không cần sửa. "
                            + dump({"preferences": content_preferences(prefs), "unit": {k:unit[k] for k in ('title','objective')}, "scope": body.target, "request": body.request, "current_content": before})
                            + language_instruction(prefs) + chapter_instruction
                            + ' Bản đọc chương chỉ định hướng. source_refs của bản sửa phải thuộc đúng nguyên văn của bài được gửi; nếu thiếu căn cứ thì báo thiếu, không suy nguồn từ bản tóm tắt. ')
                        replacement = validate_replacement(await generate_checked(schema, instruction, fragments))
                        replacement_input_strategy = correction_prompt.FULL_CONTENT_STRATEGY
                except QuestionRejected as exc:
                    rejection = exc.details; checkpoint()
                    raise ProviderError(exc.code, str(exc)) from exc
                replacement_provider = identity['provenance']
            validate_language(replacement, prefs)
            checkpoint()
            provenance = {'job_id': job_id, 'provider': replacement_provider, 'scope': scope, 'input_strategy': replacement_input_strategy,
                          'chapter_context': chapter_progress, 'before_sha256': correction_context.digest(before),
                          'after_sha256': correction_context.digest(replacement), 'resumed_from_job_id': body.resume_job_id,
                          'created_at': now()}
            return save_proposal(replacement, job_id, provenance)
        return new_job(owner, "correction", payload, background, work, identity)

    @app.get("/api/proposals/{proposal_id}")
    def get_proposal(proposal_id: str, owner=Depends(user)):
        with database.connection() as db:
            proposal = owned(db, "revision_proposals", proposal_id, owner)
            if active_exam(db, owner, proposal["course_id"]) or (json.loads(proposal['scope_json']).get('target') == 'question_completion' and rooms.active(db, owner, proposal['course_id'])):
                raise HTTPException(403, "Xem đề xuất và đáp án sau lượt kiểm tra.")
        value = json.loads(proposal["content_json"])
        result = {"id": proposal_id, "course_id": proposal["course_id"], "base_revision": proposal["base_revision"], "scope": json.loads(proposal["scope_json"]), "request": proposal["request"], "status": proposal["status"], "before": value["before"], "after": value["after"]}
        if 'source_bindings' in value:
            result['source_bindings'] = value['source_bindings']
        return result

    @app.post("/api/proposals/{proposal_id}/apply")
    def apply_proposal(proposal_id: str, body: Version, owner=Depends(user)):
        with database.connection(write=True) as db:
            proposal = owned(db, "revision_proposals", proposal_id, owner)
            if active_exam(db, owner, proposal['course_id']) or (json.loads(proposal['scope_json']).get('target') == 'question_completion' and rooms.active(db, owner, proposal['course_id'])):
                raise HTTPException(403, 'Nộp/hủy lượt kiểm tra trước khi áp dụng bản sửa.')
            if proposal["status"] != "preview" or proposal["base_revision"] != body.expected_revision:
                raise HTTPException(409, "Đề xuất đã áp dụng hoặc không khớp bản đang xem.")
            course = course_snapshot(db, proposal["course_id"], owner)
            if course["revision"] != body.expected_revision:
                raise HTTPException(409, "Khóa học đã đổi; đề xuất được giữ, chưa ghi đè bản mới.")
            candidate = json.loads(proposal['content_json'])
            plan_id = candidate.get('plan_id', course['plan_id'])
            for guard in candidate.get('source_guards', []):
                source = source_snapshot(db, guard['source_id'], owner)
                if not source['reviewed'] or source['revision'] != guard['extraction_revision']:
                    raise HTTPException(409, 'Nguồn đã đổi sau khi xem trước; kiểm tra bản trích và tạo đề xuất mới.')
            for target_id in candidate.get('plan_ids', [plan_id]):
                target_plan = owned(db, 'plans', target_id, owner)
                if target_plan['status'] == 'proposal_preview':
                    db.execute("UPDATE plans SET status='approved',approved_at=? WHERE id=?", (now(), target_id))
                elif target_plan['status'] != 'approved':
                    raise HTTPException(409, 'Bản phác thảo cần được duyệt trước khi áp dụng.')
            result = commit_course(db, course, owner, candidate["content"], plan_id)
            db.execute("UPDATE revision_proposals SET status='applied' WHERE id=?", (proposal_id,))
            return result

    @app.post("/api/proposals/{proposal_id}/discard")
    def discard_proposal(proposal_id: str, owner=Depends(user)):
        with database.connection(write=True) as db:
            proposal = owned(db, "revision_proposals", proposal_id, owner)
            if proposal["status"] != "preview":
                raise HTTPException(409, "Đề xuất không còn ở bước xem trước.")
            db.execute("UPDATE revision_proposals SET status='discarded' WHERE id=?", (proposal_id,))
            candidate = json.loads(proposal['content_json'])
            for candidate_plan in candidate.get('plan_ids', [candidate.get('plan_id')]):
                if candidate_plan:
                    db.execute("UPDATE plans SET status='discarded' WHERE id=? AND status='proposal_preview'", (candidate_plan,))
        return {"status": "discarded"}

    def course_overview(db, owner, course):
        """Summary and key ideas the AI wrote after reading the creator's whole approved scope."""
        try:
            plan = course_plan(db, course, owner)
            binding = chapters.binding(plan, course['creator_id'], approved_fragments(db, plan, course['creator_id']))
            root = chapters.stored(db, binding).get(binding['manifest']['root'])
        except (HTTPException, ValueError, KeyError):
            return None
        return {'summary': root['brief']['summary'], 'key_ideas': root['brief']['key_ideas'][:6]} if root else None

    def ai_memory(db, owner, course_id):
        course = course_snapshot(db, course_id, owner)
        return memory_for_ai(db, owner, course, course_overview(db, owner, course))

    @app.post("/api/courses/{course_id}/chat")
    async def chat(course_id: str, body: ChatRequest, background: BackgroundTasks, request: Request, owner=Depends(user)):
        payload = {**body.model_dump(), "course_id": course_id}
        identity = jobs.identity(request, "chat", payload, owner=owner)
        with database.connection() as db:
            course = course_snapshot(db, course_id, owner)
            if active_test(db, owner, course_id):
                raise HTTPException(403, "Chat giải bài mở sau lượt kiểm tra; không gọi AI trong lượt đang tính điểm.")
            history = [dict(r) for r in db.execute("SELECT role,content,revision FROM chat_messages WHERE owner_id=? AND course_id=? ORDER BY created_at DESC LIMIT 6", (owner, course_id))][::-1]
            object_context = None
            refs = None
            if body.session_id and body.card_id:
                raise HTTPException(422, 'Chọn một ngữ cảnh câu hoặc thẻ cho mỗi lần hỏi.')
            if body.session_id:
                session = owned(db, "study_sessions", body.session_id, owner)
                if session["course_id"] != course_id:
                    raise HTTPException(422, "Lượt không thuộc khóa đang hỏi.")
                item = next((q for q in json.loads(session["items_json"]) if q["id"] == body.item_id), None)
                if not item or (item.get("unit_id") or item["id"].rsplit(":q", 1)[0]) != body.unit_id:
                    raise HTTPException(422, "Chọn đúng câu của bài đang hỏi.")
                selected = db.execute("SELECT answer_json,result_json FROM answers WHERE session_id=? AND item_id=?", (body.session_id, body.item_id)).fetchone()
                object_context = {"question": item, "learner_answer": json.loads(selected["answer_json"]) if selected else None, "course_revision": session["course_revision"]}
                course = course_snapshot(db, course_id, owner, session['course_revision'])
                refs = item['source_refs']
            elif body.item_id:
                raise HTTPException(422, "Cần ID lượt luyện để lấy đúng câu/đáp án của bạn.")
            if body.card_id:
                card = next((c for c in learning.cards(db, owner, course_id) if c["id"] == body.card_id), None)
                if not card:
                    raise HTTPException(404, "Thẻ không thuộc bộ của bạn.")
                if card['kind'] == 'generated' and card['unit_id'] != body.unit_id:
                    raise HTTPException(422, 'Chọn đúng bài của thẻ đang hỏi.')
                origin = card.get('origin', {})
                if origin.get('kind') == 'question':
                    original = owned(db, 'study_sessions', origin['session_id'], owner)
                    item = next((q for q in json.loads(original['items_json']) if q['id'] == origin['item_id']), None)
                    if original['course_id'] != course_id or not item or (item.get('unit_id') or item['id'].rsplit(':q', 1)[0]) != body.unit_id:
                        raise HTTPException(422, 'Chọn đúng bài của câu đã lưu thành thẻ.')
                    course = course_snapshot(db, course_id, owner, original['course_revision'])
                object_context = {"card": card}
                refs = card['source_refs']
            unit = unit_from(course, body.unit_id, ready=True)
            plan = course_plan(db, course, owner, unit)
            if refs is not None and not set(refs) <= set(unit['source_refs']):
                raise HTTPException(422, 'Nguồn thẻ không thuộc bài/phiên bản đang hỏi; chọn đúng ngữ cảnh nguồn.')
            fragments = approved_fragments(db, plan, course["creator_id"], refs or unit['source_refs'])
            memory = ai_memory(db, owner, course_id)
        previous = jobs.cached(owner, identity, active=False)
        if previous:
            return previous
        identity["fingerprint"] = jobs.identity(None, "chat", {**payload, "course_revision": course["revision"]}, owner=owner)["fingerprint"]

        def prepare(db):
            if body.session_id and session["status"] == "open":
                db.execute("INSERT OR IGNORE INTO assistance_events VALUES (?,?,?,?)", (body.session_id, body.item_id, "ai_help", now()))
                db.execute("UPDATE answers SET assisted=1 WHERE session_id=? AND item_id=?", (body.session_id, body.item_id))
            db.execute("INSERT INTO chat_messages VALUES (?,?,?,?,?,?,?,?)", (new_id(), owner, course_id, course["revision"], "user", body.message, "[]", now()))

        async def work(job_id):
            # The latest message is repeated last so a long history cannot bury it.
            instruction = chat_prompt.COURSE_CHAT + (MEMORY_RULE if memory else "") + dump({"assistant": chat_prompt.assistant(identity["provenance"]), "language": json.loads(plan["preferences_json"])["language"], "course_revision": course["revision"], "source_id": plan['source_id'], "extraction_revision": json.loads(plan['preferences_json'])['extraction_revision'], "unit": unit["title"], "object_context": object_context, "history": history, "question": body.message, **({"course_memory": memory} if memory else {})}) + "\nTin nhắn mới nhất cần trả lời: " + body.message
            reply = await generate_checked(ChatReply, instruction, fragments)
            with database.connection(write=True) as db:
                jobs.check(db, job_id)
                db.execute("INSERT INTO chat_messages VALUES (?,?,?,?,?,?,?,?)", (new_id(), owner, course_id, course["revision"], "assistant", reply["text"], dump(reply["source_refs"]), now()))
                jobs.finish(db, job_id, reply)
            return reply
        return new_job(owner, "chat", payload, background, work, identity, prepare)

    @app.get("/api/courses/{course_id}/chat")
    def chat_history(course_id: str, owner=Depends(user)):
        with database.connection() as db:
            course = course_snapshot(db, course_id, owner)
            if active_test(db, owner, course_id):
                raise HTTPException(403, 'Chat được mở lại sau lượt kiểm tra/phòng đang tính điểm.')
            rows = db.execute("SELECT * FROM chat_messages WHERE owner_id=? AND course_id=? ORDER BY created_at DESC,id DESC LIMIT 100", (owner, course_id)).fetchall()
            return [{"id": r["id"], "role": r["role"], "text": r["content"], "source_refs": json.loads(r["refs_json"]), "revision": r["revision"]} for r in reversed(rows)]

    @app.get("/api/source-limits")
    def source_limits():
        return public_limits()

    @app.get('/api/health')
    def health():
        # Loading saved sources must not wait for a sleeping/offline remote model.
        return {'backend':True,'provider_health_checked':False}

    @app.get("/api/status")
    async def status(request: Request):
        try:
            owner = user(request)
        except HTTPException:
            owner = None
        return {"backend": True, "ai": await ai.status(owner), "input_types": ["txt", "md", "docx", "pdf", "pptx", "png", "jpg", "jpeg", "webp", "tiff", "bmp", "heic", "public_article"], "ocr": {"engine": "macOS_Vision", "requires_review": True}, "public_links": True}

    @app.post("/api/session")
    def session(request: Request, response: Response):
        try:
            owner = user(request)
        except HTTPException:
            owner, token = new_id(), secrets.token_urlsafe(32)
            with database.connection(write=True) as db:
                db.execute("INSERT INTO users VALUES (?,?,?,?,?)", (owner, owner + "@local.invalid", "Người học local", "anonymous-local", now()))
                db.execute("INSERT INTO auth_sessions VALUES (?,?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), owner, int(time.time()) + 30 * 86400, now()))
            response.set_cookie("study_session", token, httponly=True, samesite="strict", max_age=30 * 86400)
        return {"id": owner, "kind": "anonymous_local", "warning": "Lưu cookie để trở lại dữ liệu riêng. Đây chưa phải đăng nhập tài khoản công khai."}

    def job_snapshot(job_id: str, owner):
        with database.connection(write=True) as db:
            value = owned(db, "jobs", job_id, owner)
            payload = json.loads(value['payload_json'])
            course_id = payload.get("course_id")
            withheld = bool(course_id and active_test(db, owner, course_id))
            progress = job_progress.read(db, job_id)
            if withheld and progress: progress['preview'] = None
        partial = json.loads(value["partial_json"])
        if withheld:
            # A reading, card, focus hint or corrected replacement can disclose
            # an answer even without an `answer` key. Keep only coverage, not
            # AI content, while the server defers feedback. Stored data is intact.
            partial = {'chapter_context': partial.get('chapter_context'), 'questions': {}}
        context = {k: payload[k] for k in ('course_id', 'unit_id', 'expected_revision', 'course_revision', 'thread_id', 'room_id', 'question_id', 'session_id', 'item_id', 'plan_id', 'source_id', 'asset_id', 'ocr_batch_id') if k in payload}
        if value['task'] == 'correction' and not withheld:
            context.update({k:payload[k] for k in ('target', 'index', 'request') if k in payload})
        error = json.loads(value['error_json']) if value['error_json'] else None
        if withheld and error:
            error = {'code': 'FEEDBACK_DEFERRED', 'message': 'Lượt AI đã dừng; xem phản hồi sau khi nộp/hủy lượt kiểm tra.'}
        return {"id": job_id, "task": value['task'], "context": context, "status": value["status"], "attempts": value["attempts"], "provider": payload.get('_provider', {'provider': 'legacy_unrecorded'}), "result": json.loads(value["result_json"]) if value["result_json"] and not withheld else None, "partial": partial, "feedback_deferred": withheld, "error": error, 'progress': progress}

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str, owner=Depends(user)):
        return job_snapshot(job_id, owner)

    register_job_events(app, job_snapshot, user)

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str, owner=Depends(user)):
        return jobs.cancel(owner, job_id)

    def save_source(owner, name, data, prepared=None, extra_metadata=None):
        if not data or len(data) > MAX_BYTES:
            raise HTTPException(422, "File rỗng hoặc vượt giới hạn 50 MiB.")
        source_id = new_id()
        path = storage / source_id
        path.write_bytes(data)
        metadata = {"name": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "warnings": [], "subject_suggestion": "", **(extra_metadata or {})}
        try:
            with database.connection(write=True) as db:
                for component in metadata.get('components',[]):
                    current=source_snapshot(db,component['source_id'],owner)
                    if current['revision']!=component['extraction_revision']:
                        raise HTTPException(409,'Tài liệu thành phần đã đổi trong lúc gộp; chọn lại phạm vi trước khi tạo bộ nguồn.')
                db.execute("INSERT INTO sources VALUES (?,?,?,?,?)", (source_id, owner, dump(metadata), "parsing", now()))
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        try:
            fragments, warnings = prepared or read_source(name, data)
            if not fragments or len(fragments) > MAX_FRAGMENTS or sum(len(f["text"]) for f in fragments) > MAX_TEXT:
                raise ValueError("Bản trích rỗng hoặc vượt giới hạn; cần chia nguồn/nhập lại trước khi tạo bài.")
        except Exception as exc:
            message = str(exc) if isinstance(exc, ValueError) else "File chưa đọc được bằng bộ trích hiện tại. File gốc được giữ để thử lại hoặc thay nguồn."
            metadata["warnings"] = [message]
            with database.connection(write=True) as db:
                db.execute("UPDATE sources SET metadata_json=?,status='failed' WHERE id=?", (dump(metadata), source_id))
            raise HTTPException(422, {"message": message, "source_id": source_id, "original_retained": True}) from exc
        for i, fragment in enumerate(fragments):
            fragment.update(id=f"{source_id}:1:{i}", original_text=fragment["text"])
        metadata.update(warnings=warnings, subject_suggestion='')
        try:
            with database.connection(write=True) as db:
                db.execute("UPDATE sources SET metadata_json=?,status='needs_review' WHERE id=?", (dump(metadata), source_id))
                db.execute("INSERT INTO extraction_revisions VALUES (?,?,?,?,?)", (source_id, 1, dump(fragments), None, now()))
        except Exception as exc:
            raise HTTPException(500, {"message": "Chưa lưu được bản trích; file gốc còn nguyên để thử lại.", "source_id": source_id, "original_retained": True}) from exc
        return {"id": source_id, "metadata": metadata, "status": "needs_review", "revision": 1, "reviewed": False, "fragments": fragments}

    register_source_collections(app, database, source_snapshot, user, save_source)

    @app.post("/api/sources/upload")
    async def upload(file: UploadFile = File(...), owner=Depends(user)):
        data = await file.read(MAX_BYTES + 1)
        await file.close()
        name = (file.filename or "file").replace("\\", "/").split("/")[-1][:200]
        return await asyncio.to_thread(save_source, owner, name, data)

    @app.post("/api/sources/text")
    async def text_source(body: TextSource, owner=Depends(user)):
        return await asyncio.to_thread(save_source, owner, body.name + ".txt", body.text.encode("utf-8"))

    @app.post("/api/sources/url")
    async def url_source(body: URLSource, owner=Depends(user)):
        try:
            article = await read_article(body.url)
            fragments = article.get("fragments") or extract("article.txt", article["text"].encode("utf-8"), ocr=False)[0]
            for fragment in fragments:
                fragment["locator"].update(type="article", url=article["url"])
            warnings = ["Bài viết được lưu thành snapshot. Đối chiếu nội dung/công thức với snapshot trước khi tạo."]
            return await asyncio.to_thread(save_source, owner, article["title"][:180] + ".html", article["original"], (fragments, warnings), {"url": article["url"], "fetched_at": now(), "content_type": article["content_type"]})
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/sources")
    def sources(response:Response,q:str=Query(default='',max_length=120),reviewed:bool|None=None,
                limit:int=Query(default=100,ge=1,le=100),cursor:str|None=Query(default=None,max_length=2048),owner=Depends(user)):
        page=source_library.page(owner,q,reviewed,limit,cursor)
        response.headers['X-Source-Total']=str(page['total'])
        response.headers['X-Current-Cursor']=page['current_cursor'] or ''
        response.headers['X-Next-Cursor']=page['next_cursor'] or ''
        response.headers['Link']='</api/source-library>; rel="collection"'
        with database.connection() as db:
            result = []
            for row in page['items']:
                value = source_snapshot(db, row["id"], owner)
                result.append({k: v for k, v in value.items() if k != "fragments"})
            return result

    @app.get("/api/sources/{source_id}")
    def source(source_id: str, revision: int | None = None, owner=Depends(user)):
        with database.connection() as db:
            return source_snapshot(db, source_id, owner, revision)

    @app.get("/api/sources/{source_id}/original")
    def original(source_id: str, owner=Depends(user)):
        with database.connection() as db:
            try:
                source = source_snapshot(db, source_id, owner)
            except HTTPException as exc:
                if exc.status_code != 404 or not community.can_original(db, source_id, owner):
                    raise
                row = db.execute('SELECT metadata_json FROM sources WHERE id=?', (source_id,)).fetchone()
                if not row: raise HTTPException(404, 'Không có file gốc được chia sẻ.')
                source = {'metadata': json.loads(row[0])}
        return FileResponse(storage / source_id, filename=source["metadata"]["name"], media_type="application/octet-stream")

    def save_source_texts(source_id, body, owner, confirm):
        with database.connection(write=True) as db:
            source = source_snapshot(db, source_id, owner)
            if source["revision"] != body.expected_revision:
                raise HTTPException(409, "Bản trích đã thay đổi; tải lại trước khi lưu.")
            if len(body.texts) != len(source["fragments"]) or sum(map(len, body.texts)) > MAX_TEXT or any(not x.strip() or len(x) > 5000 for x in body.texts):
                raise HTTPException(422, "Giữ số đoạn và nhập nội dung hợp lệ cho mỗi đoạn.")
            revision = source["revision"] + 1
            fragments = [{**fragment, "id": f"{source_id}:{revision}:{i}", "text": body.texts[i].strip(), "edited_by_user": body.texts[i].strip() != fragment["original_text"], 'needs_review':False if confirm else fragment.get('needs_review',True) or body.texts[i].strip()!=fragment['text'], 'review_status':'user_confirmed_not_accuracy_verified' if confirm else 'manual_draft_not_confirmed'} for i, fragment in enumerate(source["fragments"])]
            from .office_math import UNREADABLE
            for old,fragment in zip(source['fragments'],fragments):
                if old['locator'].get('unreadable_math') and fragment['text']!=old['text'] and UNREADABLE not in fragment['text']:
                    fragment['locator']={**fragment['locator'],'unreadable_math':False,'manual_math_correction':True}
            db.execute("INSERT INTO extraction_revisions VALUES (?,?,?,?,?)", (source_id, revision, dump(fragments), now() if confirm else None, now()))
            db.execute("UPDATE sources SET status=? WHERE id=?", ('ready' if confirm else 'needs_review',source_id))
            return source_snapshot(db, source_id, owner)

    @app.post("/api/sources/{source_id}/review")
    def review_source(source_id: str, body: SourceReview, owner=Depends(user)):
        return save_source_texts(source_id,body,owner,True)

    @app.post("/api/sources/{source_id}/save-draft")
    def source_draft(source_id: str, body: SourceReview, owner=Depends(user)):
        return save_source_texts(source_id,body,owner,False)

    @app.post("/api/sources/{source_id}/transcription")
    def transcribe_source(source_id: str, body: SourceTranscription, owner=Depends(user)):
        fragments, warnings = extract("transcription.txt", body.text.encode("utf-8"), ocr=False)
        # Manual transcription is explicitly separate from what the reader saw.
        # It does not assert a page/box location that was never verified.
        with database.connection(write=True) as db:
            source = source_snapshot(db, source_id, owner)
            if source["revision"] != body.expected_revision:
                raise HTTPException(409, "Bản trích đã đổi; tải lại trước khi bổ sung chữ.")
            revision = source["revision"] + 1
            for i, fragment in enumerate(fragments):
                fragment.update(id=f"{source_id}:{revision}:{i}", original_text=fragment["text"], edited_by_user=True, needs_review=True)
                fragment["locator"].update(type="user_transcription", source_original=source_id, location_unverified=True)
            metadata = source["metadata"]
            metadata["warnings"] = list(dict.fromkeys(metadata["warnings"] + warnings + ["Bản chép tay do người học bổ sung; vị trí trong bản gốc chưa được xác minh."]))
            db.execute("INSERT INTO extraction_revisions VALUES (?,?,?,?,?)", (source_id, revision, dump(fragments), None, now()))
            db.execute("UPDATE sources SET status='needs_review',metadata_json=? WHERE id=?", (dump(metadata), source_id))
            return source_snapshot(db, source_id, owner)

    @app.post("/api/sources/{source_id}/retry-extraction")
    async def retry_source(source_id: str, body: Version, owner=Depends(user)):
        with database.connection() as db:
            source = source_snapshot(db, source_id, owner)
        if source["revision"] != body.expected_revision:
            raise HTTPException(409, "Bản trích đã đổi; tải lại trước khi thử đọc lại.")
        if source["metadata"].get("kind") == "collection":
            raise HTTPException(422, "Bộ nguồn là snapshot. Đọc/sửa tài liệu thành phần rồi tạo bộ nguồn mới; không tự đổi bản đang học.")
        data = await asyncio.to_thread((storage / source_id).read_bytes)
        try:
            if source["metadata"].get("url"):
                article = parse_article(data, source["metadata"]["content_type"], source["metadata"]["url"], "Saved article")
                fragments, warnings = article["fragments"], ["Đọc lại snapshot đã lưu; không tải lại bài viết trên mạng."]
            else:
                fragments, warnings = await asyncio.to_thread(read_source, source["metadata"]["name"], data)
        except ValueError as exc:
            raise HTTPException(422, {"message": str(exc), "source_id": source_id, "original_retained": True}) from exc
        with database.connection(write=True) as db:
            current = source_snapshot(db, source_id, owner)
            if current["revision"] != body.expected_revision:
                raise HTTPException(409, "Một lượt đọc/sửa khác đã lưu trước; bản hiện tại được giữ.")
            revision = current["revision"] + 1
            for i, fragment in enumerate(fragments):
                fragment.update(id=f"{source_id}:{revision}:{i}", original_text=fragment["text"])
            metadata = current["metadata"]
            metadata["warnings"] = warnings
            db.execute("INSERT INTO extraction_revisions VALUES (?,?,?,?,?)", (source_id, revision, dump(fragments), None, now()))
            db.execute("UPDATE sources SET status='needs_review',metadata_json=? WHERE id=?", (dump(metadata), source_id))
            return source_snapshot(db, source_id, owner)

    register_learning(app, learning, user, activity)
    source_library=register_source_library(app,database,source_snapshot,user)
    register_source_review(app, database, storage, ai, jobs, source_snapshot, owned, user, page_renderer)
    register_source_ocr(app, database, storage, jobs, source_snapshot, owned, user, native_ocr_reader, native_frame_counter)
    register_setup(app, database, jobs, source_snapshot, owned, user, generate_checked)
    register_revisions(app, database, course_snapshot, source_snapshot, owned, active_exam, reader_course, user)
    register_question_completion(app, database, jobs, owned, user, course_snapshot, course_plan, unit_from, approved_fragments, active_test, generate_checked, chapters)
    register_feedback(app, database, jobs, owned, course_snapshot, approved_fragments, active_test, generate_checked, user)
    register_economy(app, economy, database, user)
    register_activity(app, activity, user)
    register_community(app, community, database, course_snapshot, owned, user, economy)
    register_inline_help(app, database, jobs, owned, user, course_snapshot, course_plan, unit_from, approved_fragments, active_test, generate_checked, ai_memory)
    register_course_memory(app, database, course_snapshot, user, course_overview)
    register_blueprint(app, database, jobs, source_snapshot, user, generate_checked, ai.source_budget)
    register_accounts(app, database)
    register_covers(app, database, course_snapshot, owned, community.ids, user)
    register_providers(app, ai, database, user)
    register_rooms(app, rooms, database, user, course_snapshot, course_plan, approved_fragments, unit_from, owned, active_test, jobs, generate_checked)
    register_lifecycle(app,database,jobs,rooms,storage,user)
    # The rebuilt interface (web/, built into web/dist) is served at "/" once built;
    # the previous interface stays reachable at /legacy/ until every screen is rebuilt.
    web = ROOT / "web" / "dist"
    app.mount("/legacy", StaticFiles(directory=ROOT / "frontend", html=True), name="legacy")
    app.mount("/", StaticFiles(directory=web if (web / "index.html").is_file() else ROOT / "frontend", html=True), name="frontend")
    return app


