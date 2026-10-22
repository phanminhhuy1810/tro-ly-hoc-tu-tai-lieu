"""SQLite persistence with transactional writes and explicit schema versioning."""

from contextlib import contextmanager
from pathlib import Path
import sqlite3


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_versions(version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO schema_versions VALUES (1);
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name TEXT NOT NULL, password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
    expires_at INTEGER NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
    metadata_json TEXT NOT NULL, status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fragments (
    id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
    text TEXT NOT NULL, locator_json TEXT NOT NULL, kind TEXT NOT NULL,
    warnings_json TEXT NOT NULL, ordinal INTEGER NOT NULL,
    UNIQUE(source_id, ordinal)
);
CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
    source_id TEXT NOT NULL REFERENCES sources(id), preferences_json TEXT NOT NULL,
    outline_json TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
    approved_at TEXT
);
CREATE TABLE IF NOT EXISTS courses (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
    active_revision INTEGER NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS course_revisions (
    course_id TEXT NOT NULL REFERENCES courses(id), revision INTEGER NOT NULL,
    plan_id TEXT NOT NULL REFERENCES plans(id), content_json TEXT NOT NULL,
    created_at TEXT NOT NULL, PRIMARY KEY(course_id, revision)
);
CREATE TABLE IF NOT EXISTS study_sessions (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
    course_id TEXT NOT NULL, course_revision INTEGER NOT NULL,
    mode TEXT NOT NULL, exam INTEGER NOT NULL, scope_json TEXT NOT NULL,
    items_json TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
    completed_at TEXT, result_json TEXT,
    FOREIGN KEY(course_id, course_revision) REFERENCES course_revisions(course_id, revision)
);
CREATE TABLE IF NOT EXISTS answers (
    session_id TEXT NOT NULL REFERENCES study_sessions(id), item_id TEXT NOT NULL,
    answer_json TEXT NOT NULL, result_json TEXT NOT NULL,
    assisted INTEGER NOT NULL, answered_at TEXT NOT NULL,
    PRIMARY KEY(session_id, item_id)
);
CREATE TABLE IF NOT EXISTS unit_completions (
    owner_id TEXT NOT NULL REFERENCES users(id), course_id TEXT NOT NULL,
    course_revision INTEGER NOT NULL, unit_id TEXT NOT NULL,
    session_id TEXT NOT NULL REFERENCES study_sessions(id), completed_at TEXT NOT NULL,
    PRIMARY KEY(owner_id, course_id, course_revision, unit_id),
    FOREIGN KEY(course_id, course_revision) REFERENCES course_revisions(course_id, revision)
);
CREATE TABLE IF NOT EXISTS notebook_entries (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
    body TEXT NOT NULL, label TEXT NOT NULL, refs_json TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
    task TEXT NOT NULL, payload_json TEXT NOT NULL, status TEXT NOT NULL,
    attempts INTEGER NOT NULL, max_attempts INTEGER NOT NULL,
    result_json TEXT, partial_json TEXT NOT NULL, error_json TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS wallets (
    owner_id TEXT PRIMARY KEY REFERENCES users(id), balance INTEGER NOT NULL CHECK(balance>=0)
);
CREATE TABLE IF NOT EXISTS coin_ledger (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
    amount INTEGER NOT NULL, reason TEXT NOT NULL, event_key TEXT NOT NULL,
    created_at TEXT NOT NULL, UNIQUE(owner_id, event_key)
);
CREATE TABLE IF NOT EXISTS coin_reservations (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
    amount INTEGER NOT NULL CHECK(amount>0), purpose TEXT NOT NULL,
    job_id TEXT REFERENCES jobs(id), status TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS idempotency (
    owner_id TEXT NOT NULL REFERENCES users(id), operation TEXT NOT NULL,
    request_key TEXT NOT NULL, digest TEXT NOT NULL, result_json TEXT NOT NULL,
    created_at TEXT NOT NULL, PRIMARY KEY(owner_id, operation, request_key)
);
CREATE INDEX IF NOT EXISTS sources_owner ON sources(owner_id);
CREATE INDEX IF NOT EXISTS plans_owner ON plans(owner_id);
CREATE INDEX IF NOT EXISTS sessions_owner_course ON study_sessions(owner_id, course_id);
CREATE INDEX IF NOT EXISTS notebook_owner ON notebook_entries(owner_id);
CREATE INDEX IF NOT EXISTS jobs_owner ON jobs(owner_id);
CREATE TABLE IF NOT EXISTS extraction_revisions (
    source_id TEXT NOT NULL REFERENCES sources(id), revision INTEGER NOT NULL,
    content_json TEXT NOT NULL, reviewed_at TEXT, created_at TEXT NOT NULL,
    PRIMARY KEY(source_id, revision)
);
CREATE TABLE IF NOT EXISTS revision_proposals (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
    course_id TEXT NOT NULL REFERENCES courses(id), base_revision INTEGER NOT NULL,
    scope_json TEXT NOT NULL, request TEXT NOT NULL, content_json TEXT NOT NULL,
    status TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
    course_id TEXT NOT NULL REFERENCES courses(id), revision INTEGER NOT NULL,
    role TEXT NOT NULL, content TEXT NOT NULL, refs_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
INSERT OR IGNORE INTO schema_versions VALUES (2);
CREATE TABLE IF NOT EXISTS job_fingerprints (
    job_id TEXT PRIMARY KEY REFERENCES jobs(id), owner_id TEXT NOT NULL REFERENCES users(id),
    operation TEXT NOT NULL, digest TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS job_fingerprint_lookup ON job_fingerprints(owner_id, operation, digest);
INSERT OR IGNORE INTO schema_versions VALUES (3);
CREATE TABLE IF NOT EXISTS personal_cards (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
    course_id TEXT REFERENCES courses(id), front TEXT NOT NULL, back TEXT NOT NULL,
    refs_json TEXT NOT NULL, origin_json TEXT NOT NULL, origin_key TEXT,
    version INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS personal_card_origin ON personal_cards(owner_id, origin_key) WHERE deleted_at IS NULL AND origin_key IS NOT NULL;
CREATE TABLE IF NOT EXISTS personal_card_versions (
    card_id TEXT NOT NULL REFERENCES personal_cards(id), version INTEGER NOT NULL,
    snapshot_json TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(card_id, version)
);
CREATE TABLE IF NOT EXISTS card_memory (
    owner_id TEXT NOT NULL REFERENCES users(id), card_id TEXT NOT NULL,
    remembered INTEGER NOT NULL CHECK(remembered IN (0,1)), version INTEGER NOT NULL,
    updated_at TEXT NOT NULL, PRIMARY KEY(owner_id, card_id)
);
CREATE TABLE IF NOT EXISTS notebook_versions (
    entry_id TEXT NOT NULL REFERENCES notebook_entries(id), version INTEGER NOT NULL,
    snapshot_json TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(entry_id, version)
);
CREATE TABLE IF NOT EXISTS notebook_deleted (entry_id TEXT PRIMARY KEY REFERENCES notebook_entries(id), deleted_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notebook_origins (
    entry_id TEXT PRIMARY KEY REFERENCES notebook_entries(id), owner_id TEXT NOT NULL,
    kind TEXT NOT NULL, origin_id TEXT NOT NULL, revision INTEGER NOT NULL,
    UNIQUE(owner_id, kind, origin_id)
);
CREATE TABLE IF NOT EXISTS learning_progress (
    owner_id TEXT NOT NULL REFERENCES users(id), course_id TEXT NOT NULL REFERENCES courses(id),
    position_json TEXT NOT NULL, version INTEGER NOT NULL, updated_at TEXT NOT NULL,
    PRIMARY KEY(owner_id, course_id)
);
CREATE TABLE IF NOT EXISTS learning_mode_progress (
    owner_id TEXT NOT NULL REFERENCES users(id), course_id TEXT NOT NULL REFERENCES courses(id),
    mode TEXT NOT NULL, position_json TEXT NOT NULL, updated_at TEXT NOT NULL,
    PRIMARY KEY(owner_id, course_id, mode)
);
CREATE TABLE IF NOT EXISTS assistance_events (
    session_id TEXT NOT NULL REFERENCES study_sessions(id), item_id TEXT NOT NULL,
    kind TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(session_id,item_id,kind)
);
CREATE TABLE IF NOT EXISTS session_drafts (
    session_id TEXT NOT NULL REFERENCES study_sessions(id), item_id TEXT NOT NULL,
    answer_json TEXT NOT NULL, version INTEGER NOT NULL, updated_at TEXT NOT NULL,
    PRIMARY KEY(session_id, item_id)
);
CREATE TABLE IF NOT EXISTS question_review_flags (
    course_id TEXT NOT NULL REFERENCES courses(id), question_revision_id TEXT NOT NULL,
    state TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL,
    PRIMARY KEY(course_id, question_revision_id)
);
INSERT OR IGNORE INTO schema_versions VALUES (4);
CREATE TABLE IF NOT EXISTS source_proposals (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
    source_id TEXT NOT NULL REFERENCES sources(id), base_revision INTEGER NOT NULL,
    page INTEGER NOT NULL, page_kind TEXT NOT NULL, content_json TEXT NOT NULL,
    status TEXT NOT NULL, created_at TEXT NOT NULL
);
INSERT OR IGNORE INTO schema_versions VALUES (5);
CREATE TABLE IF NOT EXISTS source_analyses (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
    source_id TEXT NOT NULL REFERENCES sources(id), extraction_revision INTEGER NOT NULL,
    content_json TEXT NOT NULL, created_at TEXT NOT NULL
);
INSERT OR IGNORE INTO schema_versions VALUES (6);
CREATE TABLE IF NOT EXISTS short_feedback (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
    session_id TEXT NOT NULL REFERENCES study_sessions(id), item_id TEXT NOT NULL,
    course_revision INTEGER NOT NULL, content_json TEXT NOT NULL, created_at TEXT NOT NULL,
    UNIQUE(owner_id, session_id, item_id)
);
INSERT OR IGNORE INTO schema_versions VALUES (7);
CREATE TABLE IF NOT EXISTS course_publications (
    course_id TEXT PRIMARY KEY REFERENCES courses(id), visibility TEXT NOT NULL,
    source_ids_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS course_members (
    course_id TEXT NOT NULL REFERENCES courses(id), user_id TEXT NOT NULL REFERENCES users(id),
    status TEXT NOT NULL, joined_at TEXT NOT NULL, PRIMARY KEY(course_id,user_id)
);
CREATE TABLE IF NOT EXISTS course_invites (
    token_hash TEXT PRIMARY KEY, course_id TEXT NOT NULL REFERENCES courses(id), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS publication_proposals (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), course_id TEXT NOT NULL REFERENCES courses(id),
    base_revision INTEGER NOT NULL, settings_json TEXT NOT NULL, summary_json TEXT NOT NULL,
    status TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS community_feedback (
    course_id TEXT NOT NULL REFERENCES courses(id), user_id TEXT NOT NULL REFERENCES users(id),
    liked INTEGER NOT NULL CHECK(liked IN (0,1)), rating INTEGER CHECK(rating BETWEEN 1 AND 5), updated_at TEXT NOT NULL,
    PRIMARY KEY(course_id,user_id)
);
CREATE TABLE IF NOT EXISTS community_quality_events (
    id TEXT PRIMARY KEY, course_id TEXT NOT NULL REFERENCES courses(id), owner_id TEXT NOT NULL REFERENCES users(id),
    actor_id TEXT NOT NULL REFERENCES users(id), reason TEXT NOT NULL, created_at TEXT NOT NULL,
    UNIQUE(course_id,actor_id), CHECK(owner_id!=actor_id)
);
CREATE TABLE IF NOT EXISTS community_reports (
    id TEXT PRIMARY KEY, course_id TEXT NOT NULL REFERENCES courses(id), reporter_id TEXT NOT NULL REFERENCES users(id),
    unit_id TEXT, question_id TEXT, reason TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL
);
INSERT OR IGNORE INTO schema_versions VALUES (8);
CREATE TABLE IF NOT EXISTS coin_quotes (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), operation TEXT NOT NULL,
    digest TEXT NOT NULL, provider_json TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount>=0),
    policy_json TEXT NOT NULL, status TEXT NOT NULL, expires_at REAL NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS coin_quotes_owner ON coin_quotes(owner_id,operation,digest,status);
CREATE TABLE IF NOT EXISTS ai_usage (
    job_id TEXT PRIMARY KEY REFERENCES jobs(id), owner_id TEXT NOT NULL REFERENCES users(id),
    quote_id TEXT REFERENCES coin_quotes(id), quota_group TEXT, amount INTEGER NOT NULL CHECK(amount>=0),
    policy_json TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS coin_reservation_job ON coin_reservations(job_id) WHERE job_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS coin_ledger_context (
    ledger_id TEXT PRIMARY KEY REFERENCES coin_ledger(id), category TEXT NOT NULL,
    utc_day TEXT NOT NULL, context_json TEXT NOT NULL, policy_json TEXT NOT NULL
);
INSERT OR IGNORE INTO schema_versions VALUES (9);
CREATE TABLE IF NOT EXISTS activity_profiles (
    owner_id TEXT PRIMARY KEY REFERENCES users(id), timezone TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS activity_events (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
    event_key TEXT NOT NULL, kind TEXT NOT NULL, course_id TEXT, unit_id TEXT,
    data_json TEXT NOT NULL, occurred_at TEXT NOT NULL,
    UNIQUE(owner_id,event_key)
);
CREATE INDEX IF NOT EXISTS activity_owner_time ON activity_events(owner_id,occurred_at);
CREATE TABLE IF NOT EXISTS activity_leases (
    owner_id TEXT PRIMARY KEY REFERENCES users(id), lease_id TEXT NOT NULL,
    course_id TEXT NOT NULL, unit_id TEXT NOT NULL, mode TEXT NOT NULL,
    sequence INTEGER NOT NULL, last_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS achievements (
    owner_id TEXT NOT NULL REFERENCES users(id), code TEXT NOT NULL,
    context_json TEXT NOT NULL, earned_at TEXT NOT NULL,
    PRIMARY KEY(owner_id,code)
);
INSERT OR IGNORE INTO schema_versions VALUES (10);
CREATE TABLE IF NOT EXISTS help_threads (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
    course_id TEXT NOT NULL REFERENCES courses(id), course_revision INTEGER NOT NULL,
    context_key TEXT NOT NULL, context_json TEXT NOT NULL, created_at TEXT NOT NULL,
    UNIQUE(owner_id,context_key)
);
CREATE TABLE IF NOT EXISTS help_messages (
    id TEXT PRIMARY KEY, thread_id TEXT NOT NULL REFERENCES help_threads(id),
    role TEXT NOT NULL, action TEXT NOT NULL, content_json TEXT NOT NULL,
    event_key TEXT NOT NULL, created_at TEXT NOT NULL,
    UNIQUE(thread_id,event_key)
);
CREATE TABLE IF NOT EXISTS help_drafts (
    thread_id TEXT PRIMARY KEY REFERENCES help_threads(id), text TEXT NOT NULL,
    version INTEGER NOT NULL, updated_at TEXT NOT NULL
);
INSERT OR IGNORE INTO schema_versions VALUES (11);
CREATE TABLE IF NOT EXISTS ai_preferences (
    owner_id TEXT PRIMARY KEY REFERENCES users(id), model_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK(revision>0), allow_external INTEGER NOT NULL CHECK(allow_external IN (0,1)),
    updated_at TEXT NOT NULL
);
INSERT OR IGNORE INTO schema_versions VALUES (12);
CREATE TABLE IF NOT EXISTS quiz_rooms (
    id TEXT PRIMARY KEY, creator_id TEXT NOT NULL REFERENCES users(id),
    course_id TEXT NOT NULL, course_revision INTEGER NOT NULL,
    code_hash TEXT NOT NULL UNIQUE, settings_json TEXT NOT NULL,
    bank_json TEXT NOT NULL, sources_json TEXT NOT NULL,
    phase TEXT NOT NULL, current_index INTEGER NOT NULL, closed_count INTEGER NOT NULL,
    event_index INTEGER NOT NULL, deadline REAL, created_at REAL NOT NULL,
    updated_at REAL NOT NULL, expires_at REAL NOT NULL, host_seen_at REAL NOT NULL, end_reason TEXT,
    question_event_index INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(course_id,course_revision) REFERENCES course_revisions(course_id,revision)
);
CREATE TABLE IF NOT EXISTS quiz_members (
    id TEXT PRIMARY KEY, room_id TEXT NOT NULL REFERENCES quiz_rooms(id),
    user_id TEXT NOT NULL REFERENCES users(id), nickname TEXT NOT NULL,
    state TEXT NOT NULL, joined_at REAL NOT NULL, last_seen_at REAL NOT NULL,
    UNIQUE(room_id,user_id)
);
CREATE TABLE IF NOT EXISTS quiz_answers (
    room_id TEXT NOT NULL REFERENCES quiz_rooms(id), user_id TEXT NOT NULL REFERENCES users(id),
    question_index INTEGER NOT NULL, answer_json TEXT NOT NULL,
    correct INTEGER NOT NULL CHECK(correct IN (0,1)), points INTEGER NOT NULL CHECK(points>=0),
    received_at REAL NOT NULL, event_index INTEGER NOT NULL,
    PRIMARY KEY(room_id,user_id,question_index)
);
CREATE TABLE IF NOT EXISTS quiz_events (
    room_id TEXT NOT NULL REFERENCES quiz_rooms(id), event_index INTEGER NOT NULL,
    kind TEXT NOT NULL, data_json TEXT NOT NULL, created_at REAL NOT NULL,
    PRIMARY KEY(room_id,event_index)
);
CREATE TABLE IF NOT EXISTS quiz_join_attempts (
    owner_id TEXT PRIMARY KEY REFERENCES users(id), window_start REAL NOT NULL, attempts INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS quiz_messages (
    id TEXT PRIMARY KEY, room_id TEXT NOT NULL REFERENCES quiz_rooms(id),
    user_id TEXT NOT NULL REFERENCES users(id), question_id TEXT NOT NULL,
    role TEXT NOT NULL, content_json TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS quiz_members_actor ON quiz_members(user_id,room_id);
CREATE INDEX IF NOT EXISTS quiz_rooms_phase ON quiz_rooms(phase,updated_at);
INSERT OR IGNORE INTO schema_versions VALUES (13);
CREATE TABLE IF NOT EXISTS job_progress (
    job_id TEXT PRIMARY KEY REFERENCES jobs(id), version INTEGER NOT NULL,
    content_json TEXT NOT NULL, updated_at TEXT NOT NULL
);
INSERT OR IGNORE INTO schema_versions VALUES (14);
CREATE TABLE IF NOT EXISTS source_ocr_batches (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
    source_id TEXT NOT NULL REFERENCES sources(id), base_revision INTEGER NOT NULL,
    original_sha256 TEXT NOT NULL, kind TEXT NOT NULL,
    items_json TEXT NOT NULL, results_json TEXT NOT NULL,
    state TEXT NOT NULL, version INTEGER NOT NULL, applied_revision INTEGER,
    origin_batch_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS source_ocr_owner_source ON source_ocr_batches(owner_id,source_id);
CREATE INDEX IF NOT EXISTS jobs_ocr_batch ON jobs(json_extract(payload_json,'$.ocr_batch_id')) WHERE task='source_ocr';
INSERT OR IGNORE INTO schema_versions VALUES (15);
CREATE TABLE IF NOT EXISTS source_library_entries (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL UNIQUE REFERENCES sources(id) ON DELETE CASCADE
);
INSERT INTO source_library_entries(source_id)
    SELECT s.id FROM sources s WHERE NOT EXISTS
        (SELECT 1 FROM source_library_entries l WHERE l.source_id=s.id)
    ORDER BY s.created_at,s.id;
CREATE TRIGGER IF NOT EXISTS source_library_created AFTER INSERT ON sources BEGIN
    INSERT INTO source_library_entries(source_id) VALUES (NEW.id);
END;
INSERT OR IGNORE INTO schema_versions VALUES (16);
CREATE TABLE IF NOT EXISTS resource_lifecycle (
    resource_type TEXT NOT NULL CHECK(resource_type IN ('source','course')),
    resource_id TEXT NOT NULL, owner_id TEXT NOT NULL REFERENCES users(id),
    version INTEGER NOT NULL CHECK(version>0), deleted_at TEXT,
    content_revision INTEGER NOT NULL, updated_at TEXT NOT NULL,
    PRIMARY KEY(resource_type,resource_id)
);
CREATE INDEX IF NOT EXISTS resource_trash_owner ON resource_lifecycle(owner_id,deleted_at);
CREATE TABLE IF NOT EXISTS resource_lifecycle_events (
    resource_type TEXT NOT NULL, resource_id TEXT NOT NULL, version INTEGER NOT NULL,
    owner_id TEXT NOT NULL REFERENCES users(id), action TEXT NOT NULL CHECK(action IN ('delete','restore')),
    content_revision INTEGER NOT NULL, occurred_at TEXT NOT NULL,
    PRIMARY KEY(resource_type,resource_id,version)
);
INSERT OR IGNORE INTO schema_versions VALUES (17);
CREATE TABLE IF NOT EXISTS chapter_contexts (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
    plan_id TEXT NOT NULL REFERENCES plans(id), manifest_json TEXT NOT NULL,
    nodes_json TEXT NOT NULL, status TEXT NOT NULL, version INTEGER NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS chapter_context_plan ON chapter_contexts(owner_id,plan_id);
INSERT OR IGNORE INTO schema_versions VALUES (18);
CREATE TABLE IF NOT EXISTS course_memory (
    owner_id TEXT NOT NULL REFERENCES users(id), course_id TEXT NOT NULL REFERENCES courses(id),
    notes TEXT NOT NULL, version INTEGER NOT NULL, updated_at TEXT NOT NULL,
    PRIMARY KEY(owner_id, course_id)
);
CREATE TABLE IF NOT EXISTS source_blueprints (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
    source_id TEXT NOT NULL REFERENCES sources(id), extraction_revision INTEGER NOT NULL,
    scope_sha256 TEXT NOT NULL, status TEXT NOT NULL, content_json TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS source_blueprint_scope ON source_blueprints(owner_id,source_id,extraction_revision,scope_sha256);
CREATE TABLE IF NOT EXISTS course_covers (
    course_id TEXT PRIMARY KEY REFERENCES courses(id), owner_id TEXT NOT NULL REFERENCES users(id),
    kind TEXT NOT NULL, preset TEXT, image BLOB, mime TEXT, updated_at TEXT NOT NULL
);
INSERT OR IGNORE INTO schema_versions VALUES (19);
"""


class Database:
    def __init__(self, path: str):
        self.path = str(Path(path).resolve())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript(SCHEMA)
            # Early development room snapshots may precede the separate
            # question token; roster events must not invalidate on-time answers.
            columns = {row[1] for row in db.execute('PRAGMA table_info(quiz_rooms)')}
            if 'question_event_index' not in columns:
                db.execute('ALTER TABLE quiz_rooms ADD COLUMN question_event_index INTEGER NOT NULL DEFAULT 0')
                db.execute("UPDATE quiz_rooms SET question_event_index=coalesce((SELECT max(e.event_index) FROM quiz_events e WHERE e.room_id=quiz_rooms.id AND e.kind='question_open'),0)")

    @contextmanager
    def connection(self, write: bool = False):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=15000")
        # WAL is set once by SQLite and supports simultaneous readers during a write.
        db.execute("PRAGMA journal_mode=WAL")
        try:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()
