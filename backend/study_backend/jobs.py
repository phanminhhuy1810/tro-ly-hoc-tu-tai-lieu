"""Atomic request deduplication and bounded, cancellable AI jobs."""
import asyncio
import hashlib
import json
import uuid
from contextlib import nullcontext
from datetime import datetime, timezone

from fastapi import HTTPException
from .gemini import ProviderError
from . import job_progress
from .job_progress import JobCancelled
from .generation_contract import GENERATION_PROCESSOR_VERSION
from .chapter_evidence import EVIDENCE_VERSION
from .chapter_context import CHAPTER_BRIEF_PROMPT_VERSION
from .question_focus import QUESTION_FOCUS_VERSION
from .correction_context import CORRECTION_PROMPT_VERSION
from .lifecycle import lifecycle_state, require_active
from .models import SourceReferenceError


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class JobManager:
    def __init__(self, database, provider_metadata=None, economy=None, max_active=1, provider_router=None):
        self.database = database
        self.active = {}
        self.provider_metadata = provider_metadata or {"provider": "unreported_adapter", "model": "unreported"}
        self.economy = economy
        self.max_active = max_active
        self.provider_router = provider_router
        self.timeout_seconds = 200

    def identity(self, request, task, payload, owner=None):
        key = request.headers.get("Idempotency-Key") if request else None
        if key and (len(key) > 128 or not key.strip()):
            raise HTTPException(422, "Idempotency-Key cần 1–128 ký tự.")
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        version = {"lesson": "20261023-skip-slide-noise-v28", "inline_help": "20261023-byte-conversation-v5", "chat": "20261023-byte-conversation-v5", "blueprint": "20261023-three-lessons-a-chapter-v3", "correction": "20261015-scoped-ordering-v2", "outline": "20261015-confirmed-preferences-v2", "source_vision": "20261015-vision-transcription-v1", "subject_analysis": "20261015-subject-inference-v1"}.get(task, "20261017-pinned-source-context-v2")
        model_id = None
        metadata = self.provider_metadata
        native = task == 'source_ocr'
        if native:
            metadata = {'provider':'macOS_Vision','model':'native_ocr','external':False}
            version = '20261018-native-ocr-continuation-v1'
        elif task == 'question_completion':
            version = '20261021-missing-question-kind-focus-v12'
            if self.provider_router:
                model_id, metadata = self.provider_router.identity_metadata(owner)
        elif self.provider_router:
            model_id, metadata = self.provider_router.identity_metadata(owner)
        if task == 'correction': version = CORRECTION_PROMPT_VERSION
        provenance = {**metadata, "prompt_version": version, "schema_version": 1 if native else 20 if task in {'lesson','question_completion','correction'} else 13}
        if task in {'lesson','question_completion','correction'}:
            provenance.update(processor_version=GENERATION_PROCESSOR_VERSION,chapter_evidence_version=EVIDENCE_VERSION,
                              chapter_brief_prompt_version=CHAPTER_BRIEF_PROMPT_VERSION, question_focus_version=QUESTION_FOCUS_VERSION)
        resources=[]
        with self.database.connection() as db:
            for kind,field in [('course','course_id'),('source','source_id')]:
                if payload.get(field):
                    resources.append({'type':kind,'id':payload[field],'version':lifecycle_state(db,kind,payload[field])['version']})
        fingerprint = hashlib.sha256((digest + json.dumps([provenance,resources], sort_keys=True)).encode()).hexdigest()
        return {"key": key, "operation": ("native:" if native else "ai:") + task, "digest": digest, "fingerprint": fingerprint, "provenance": provenance,
                'coin_quote_id':request.headers.get('Coin-Quote-Id') if request else None, '_ai_model_id': model_id,
                'resource_versions':resources}

    def cached(self, owner, identity, db=None, active=True):
        if db is None:
            with self.database.connection(write=True) as connection:
                return self.cached(owner, identity, connection, active)
        if identity["key"]:
            row = db.execute("SELECT digest,result_json FROM idempotency WHERE owner_id=? AND operation=? AND request_key=?", (owner, identity["operation"], identity["key"])).fetchone()
            if row:
                if row["digest"] != identity["digest"]:
                    raise HTTPException(409, "Khóa yêu cầu đã dùng cho nội dung khác; không ghi đè yêu cầu cũ.")
                return json.loads(row["result_json"])
        if not active:
            return None
        row = db.execute("SELECT j.id FROM job_fingerprints f JOIN jobs j ON j.id=f.job_id WHERE f.owner_id=? AND f.operation=? AND f.digest=? AND j.status IN ('queued','running') ORDER BY j.created_at LIMIT 1", (owner, identity["operation"], identity.get("fingerprint", identity["digest"]))).fetchone()
        if row:
            result = {"job_id": row["id"]}
            if identity["key"]:
                self.remember(db, owner, identity, result)
            return result
        return None

    def remember(self, db, owner, identity, result):
        if identity["key"]:
            db.execute("INSERT INTO idempotency VALUES (?,?,?,?,?,?)", (owner, identity["operation"], identity["key"], identity["digest"], json.dumps(result), timestamp()))

    def create(self, owner, task, payload, background, worker, identity, prepare=None):
        job_id = uuid.uuid4().hex
        decision = None
        native = task == 'source_ocr'
        provider_bound = self.provider_router is not None and identity.get('_ai_model_id') is not None
        with self.database.connection(write=True) as db:
            previous = self.cached(owner, identity, db)
            if previous:
                return previous
            for resource in identity.get('resource_versions',[]):
                require_active(db,resource['type'],resource['id'])
                if lifecycle_state(db,resource['type'],resource['id'])['version']!=resource['version']:
                    raise HTTPException(409,'Nguồn hoặc khóa vừa được xóa/khôi phục; xem lại yêu cầu trước khi gọi AI.')
            decision = self.economy.offer(db, owner, task, payload, identity) if self.economy and not native else {'amount':0}
            if not decision.get('confirmation_required'):
                count = db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]
                if count >= self.max_active:
                    raise HTTPException(429, {'code': 'SOURCE_READER_BUSY' if native else 'AI_BUSY', 'message': 'Hệ thống đang xử lý lượt khác. Yêu cầu được giữ ở trình duyệt; chưa tạo job hoặc giữ Coin. Chờ rồi thử lại, hoặc tiếp tục học nội dung đã có.', 'retryable': True, 'max_active_jobs': self.max_active}, headers={'Retry-After': '5'})
                if prepare:
                    prepare(db)
                db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (job_id, owner, task, json.dumps({**payload, "_provider": identity.get('provenance', self.provider_metadata), '_resource_lifecycle':identity.get('resource_versions',[])}, ensure_ascii=False), "queued", 0, 1, None, "{}", None, timestamp(), timestamp()))
                job_progress.initial(db, job_id)
                db.execute("INSERT INTO job_fingerprints VALUES (?,?,?,?)", (job_id, owner, identity["operation"], identity.get("fingerprint", identity["digest"])))
                if self.economy and not native:self.economy.reserve(db, owner, job_id, task, decision)
                result = {"job_id": job_id}
                self.remember(db, owner, identity, result)
        if decision.get('confirmation_required'):
            # Raise after the transaction commits the quote; neither a job nor
            # a plan/chat message/reservation was created before confirmation.
            raise HTTPException(402,{'code':'COIN_CONFIRMATION_REQUIRED',**decision})

        async def run():
            with self.database.connection(write=True) as db:
                row = db.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
                if row["status"] != "queued":
                    return
                db.execute("UPDATE jobs SET status='running',attempts=1,updated_at=? WHERE id=?", (timestamp(), job_id))
            async def invoke():
                reporter = job_progress.Reporter(self.database, job_id, task)
                with job_progress.bind(reporter), self.provider_router.pin(identity['_ai_model_id']) if provider_bound else nullcontext():
                    result = await worker(job_id)
                    if provider_bound:
                        self.provider_router.record_outcome(identity['_ai_model_id'])
                    return result
            task_handle = asyncio.create_task(invoke())
            self.active[job_id] = task_handle
            try:
                value = await asyncio.wait_for(task_handle, timeout=self.timeout_seconds)
                with self.database.connection(write=True) as db:
                    # Workers commit their output and success in one transaction.
                    row = db.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
                    if row["status"] == "running":
                        self.finish(db, job_id, value)
            except (asyncio.CancelledError, JobCancelled):
                with self.database.connection(write=True) as db:
                    db.execute("UPDATE jobs SET status='cancelled',error_json=?,updated_at=? WHERE id=? AND status IN ('queued','running')", (json.dumps({"message": "Lượt tạo đã hủy; phần đã lưu còn nguyên."}, ensure_ascii=False), timestamp(), job_id))
                    job_progress.terminal(db, job_id, 'cancelled')
                    self.failed_plan(db, job_id)
                    if self.economy:self.economy.release(db, job_id)
            except Exception as exc:
                if provider_bound:
                    self.provider_router.record_outcome(identity['_ai_model_id'], exc)
                message = exc.detail if isinstance(exc, HTTPException) else str(exc)
                error = {"message": str(message)[:800] or "Lượt tạo lỗi hoặc timeout; dữ liệu đã lưu còn nguyên."}
                if isinstance(exc, TimeoutError):
                    error.update(code='JOB_TIMEOUT', retryable=True, message=('OCR vượt thời hạn; phần đã lưu còn nguyên, chưa tự đọc lại.' if native else 'Lượt AI vượt thời hạn 200 giây; phần đã lưu còn nguyên, chưa tự gọi lại.'))
                if isinstance(exc, ProviderError):
                    error.update(code=exc.code, retryable=exc.retryable, provider=identity['provenance'])
                if isinstance(exc, SourceReferenceError):
                    error.update(code=exc.code,retryable=True,**exc.details)
                with self.database.connection(write=True) as db:
                    db.execute("UPDATE jobs SET status='failed',error_json=?,updated_at=? WHERE id=? AND status IN ('queued','running')", (json.dumps(error, ensure_ascii=False), timestamp(), job_id))
                    job_progress.terminal(db, job_id, 'failed')
                    self.failed_plan(db, job_id)
                    if self.economy:self.economy.release(db, job_id)
            finally:
                self.active.pop(job_id, None)
        background.add_task(run)
        return result

    def check(self, db, job_id):
        row = db.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row or row["status"] != "running":
            raise JobCancelled()

    def failed_plan(self, db, job_id):
        row = db.execute("SELECT task,status,payload_json FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row["task"] == "outline" and row["status"] in {"failed", "cancelled"}:
            plan_id = json.loads(row["payload_json"]).get("plan_id")
            db.execute("UPDATE plans SET status='failed' WHERE id=? AND status='generating'", (plan_id,))

    def recover_interrupted(self):
        """Reconcile durable checkpoints after acquiring the workspace lock.

        A lost response is not permission to spend again. Preserve checkpoints
        and idempotency records, release holds, and require an explicit retry.
        """
        with self.database.connection(write=True) as db:
            interrupted = [row['id'] for row in db.execute("SELECT id FROM jobs WHERE status IN ('queued','running')")]
            error = json.dumps({'code': 'SERVER_RESTARTED', 'retryable': True,
                                'message': 'Server đã khởi động lại. Phần đã lưu còn nguyên; Coin đang giữ đã được nhả. Mở lại yêu cầu để chủ động tiếp tục, chưa tự gọi AI lại.'}, ensure_ascii=False)
            for job_id in interrupted:
                db.execute("UPDATE jobs SET status='failed',error_json=?,updated_at=? WHERE id=? AND status IN ('queued','running')", (error, timestamp(), job_id))
                job_progress.terminal(db, job_id, 'failed')
                self.failed_plan(db, job_id)
            # Older releases could leave an outline labelled generating after
            # its job was interrupted. Only reconcile plans with terminal jobs.
            db.execute("""UPDATE plans SET status='failed' WHERE status='generating' AND id IN (
                SELECT json_extract(payload_json,'$.plan_id') FROM jobs
                WHERE task='outline' AND status IN ('failed','cancelled'))""")
            # Initial native extraction runs in a thread before an AI job
            # exists. A process crash must not leave that source parsing
            # forever (and impossible to retry/delete from the library).
            for row in db.execute("SELECT id,metadata_json FROM sources WHERE status='parsing'").fetchall():
                metadata=json.loads(row['metadata_json'])
                metadata['warnings']=[*metadata.get('warnings',[]),
                    'Server đã khởi động lại khi đang đọc tài liệu. File gốc được giữ; có thể thử đọc lại, bổ sung bản chép tay hoặc chuyển vào thùng rác.']
                metadata['extraction_interrupted']={'code':'SERVER_RESTARTED','at':timestamp()}
                db.execute("UPDATE sources SET status='failed',metadata_json=? WHERE id=?",(json.dumps(metadata,ensure_ascii=False),row['id']))
            if self.economy: self.economy.reconcile(db)
        return interrupted

    def finish(self, db, job_id, result):
        self.check(db, job_id)
        if self.economy:self.economy.finish(db, job_id, result)
        db.execute("UPDATE jobs SET status='succeeded',result_json=?,updated_at=? WHERE id=?", (json.dumps(result, ensure_ascii=False), timestamp(), job_id))
        job_progress.terminal(db, job_id, 'succeeded')

    def saved_stages(self, db, job_id, total, done, reused=0):
        self.check(db, job_id)
        job_progress.saved(db, job_id, total, done, reused)

    def cancel(self, owner, job_id):
        with self.database.connection(write=True) as db:
            row = db.execute("SELECT status FROM jobs WHERE id=? AND owner_id=?", (job_id, owner)).fetchone()
            if not row:
                raise HTTPException(404, "Không có yêu cầu này trong phiên của bạn.")
            if row["status"] == "succeeded":
                raise HTTPException(409, "Kết quả đã lưu; không hủy ngược lượt đã hoàn thành.")
            if row["status"] in {"failed", "cancelled"}:
                return {"id": job_id, "status": row["status"]}
            db.execute("UPDATE jobs SET status='cancelled',updated_at=? WHERE id=?", (timestamp(), job_id))
            job_progress.terminal(db, job_id, 'cancelled')
            self.failed_plan(db, job_id)
            if self.economy:self.economy.release(db, job_id)
        handle = self.active.get(job_id)
        if handle:
            handle.cancel()
        return {"id": job_id, "status": "cancelled"}
