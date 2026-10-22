"""Persistent cards, notebook, resume and version-pinned practice helpers."""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import Depends, HTTPException
from pydantic import Field, StrictInt, StrictStr

from .models import Model, grade
from .lifecycle import deleted


KINDS = {"mcq", "cloze", "matching", "ordering", "short_answer"}


def now():
    return datetime.now(timezone.utc).isoformat()


def packed(value):
    return json.dumps(value, ensure_ascii=False)


def content_id(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


def question_item(course_id, unit_id, index, question):
    return {**question, "id": f"{unit_id}:q{index}", "unit_id": unit_id, "question_revision_id": f"{course_id}:{unit_id}:{content_id(question)}"}


def public_question(question):
    value = {k: v for k, v in question.items() if k not in {"answer", "explanation", "rubric"}}
    value["payload"] = {
        "options": [{"id": f"option-{i}", "text": text} for i, text in enumerate(question.get("options", []))],
        "left": [{"id": f"left-{i}", "text": text} for i, text in enumerate(question.get("left", []))],
    }
    return value


def normalized_answer(question, answer):
    """Resolve client IDs against the pinned payload without asking a model."""
    options = {f"option-{i}": i for i in range(len(question.get("options", [])))}
    if isinstance(answer, dict):
        if question["kind"] != "matching" or set(answer) != {f"left-{i}" for i in range(len(question["left"]))}:
            raise ValueError("Ghép đủ từng ID bên trái, không thêm mục ngoài câu.")
        try:
            answer = [options[answer[f"left-{i}"]] for i in range(len(question["left"]))]
        except KeyError as exc:
            raise ValueError("ID đáp án không thuộc câu.") from exc
    elif isinstance(answer, list) and answer and all(isinstance(x, str) for x in answer):
        try:
            answer = [options[x] for x in answer]
        except KeyError as exc:
            raise ValueError("ID đáp án không thuộc câu.") from exc
    elif question["kind"] == "mcq" and isinstance(answer, str) and answer in options:
        answer = question["options"][options[answer]]
    # Older saved/browser attempts may still submit text/integer IDs. Their
    # snapshot stays valid; new clients use payload IDs.
    return answer


def grade_answer(question, answer):
    """Display order is irrelevant; IDs resolve to the pinned original payload."""
    return grade(question, normalized_answer(question, answer))


class PracticeRequest(Model):
    expected_revision: int
    unit_id: str | None = None
    unit_ids: list[str] = Field(default_factory=list, max_length=30)
    mode: str = Field(default="learn", pattern="^(learn|practice)$")
    exercise: str = Field(default="practice", pattern="^(practice|test|weak)$")
    question_types: list[str] = Field(default_factory=list, max_length=5)
    question_count: int | None = Field(default=None, ge=1, le=50)
    difficulty: str | None = Field(default=None, pattern="^(basic|applied|hard)$")


class CardBody(Model):
    front: str = Field(min_length=1, max_length=1000)
    back: str = Field(min_length=1, max_length=3000)
    course_id: str | None = None
    source_refs: list[str] = Field(default_factory=list, max_length=20)


class CardEdit(CardBody):
    expected_version: int


class MemoryBody(Model):
    course_id: str | None = None
    expected_revision: int | None = None
    expected_version: int = 0
    remembered: bool


class FromQuestion(Model):
    session_id: str
    item_id: str


# A note's colour is how the learner files it on screen, not content: it has no version history.
NoteColor = Literal["white", "butter", "peach", "pink", "lilac", "sky", "mint"]


class NoteBody(Model):
    body: str = Field(min_length=1, max_length=10000)
    label: str = Field(default="user", pattern="^(user|teacher)$")
    source_refs: list[str] = Field(default_factory=list, max_length=20)
    course_id: str | None = None
    color: NoteColor | None = None


class NoteColorBody(Model):
    color: NoteColor


class NoteEdit(NoteBody):
    expected_version: int


class FromChat(Model):
    message_id: str


class ProgressBody(Model):
    expected_version: int = 0
    expected_revision: int
    mode: str = Field(pattern="^(learn|cards|practice)$")
    unit_id: str
    card_id: str | None = None
    session_id: str | None = None
    section_index: int = Field(default=0, ge=0, le=20)
    item_id: str | None = None


class LearningStore:
    def __init__(self, database, course_snapshot, source_snapshot, unit_from, owned):
        self.database = database
        self.course = course_snapshot
        self.source = source_snapshot
        self.unit = unit_from
        self.owned = owned

    def refs(self, db, owner, refs, course_id=None):
        approved = set()
        if course_id:
            course = self.course(db, course_id, owner)
            approved.update(r for u in course['content']['units'] if course.get('access_role') == 'creator' or u['unlocked'] for r in u['source_refs'])
        for ref in refs:
            if ref in approved:
                continue
            parts = ref.split(":")
            if len(parts) != 3 or not parts[1].isdigit():
                raise HTTPException(422, "ID trích đoạn không hợp lệ.")
            source = self.source(db, parts[0], owner, int(parts[1]))
            if ref not in {f["id"] for f in source["fragments"]}:
                raise HTTPException(422, "Trích đoạn không thuộc bản nguồn này.")

    def cards(self, db, owner, course_id=None):
        values = []
        course_ids = [course_id] if course_id else [r[0] for r in db.execute("SELECT id FROM courses WHERE owner_id=? UNION SELECT m.course_id FROM course_members m JOIN course_publications p ON p.course_id=m.course_id WHERE m.user_id=? AND m.status='active' AND p.visibility!='private'", (owner,owner))]
        for selected_course in course_ids:
            if deleted(db,'course',selected_course):continue
            course = self.course(db, selected_course, owner)
            for unit in course["content"]["units"]:
                if not unit["unlocked"] or not unit.get("data"):
                    continue
                for card in unit["data"]["cards"]:
                    values.append({**card, "id": f"{selected_course}:{unit['id']}:card:{content_id(card)}", "kind": "generated", "course_id": selected_course, "course_revision": course["revision"], "unit_id": unit["id"], "version": 1})
        query = "SELECT * FROM personal_cards WHERE owner_id=? AND deleted_at IS NULL"
        args = [owner]
        if course_id:
            query += " AND course_id=?"; args.append(course_id)
        for row in db.execute(query + " ORDER BY created_at", args):
            values.append({"id": row["id"], "kind": "personal", "course_id": row["course_id"], "front": row["front"], "back": row["back"], "source_refs": json.loads(row["refs_json"]), "origin": json.loads(row["origin_json"]), "version": row["version"]})
        memories = {r["card_id"]: dict(r) for r in db.execute("SELECT * FROM card_memory WHERE owner_id=?", (owner,))}
        for value in values:
            memory = memories.get(value["id"])
            value["memory"] = {"remembered": bool(memory["remembered"]), "version": memory["version"], "updated_at": memory["updated_at"]} if memory else {"remembered": None, "version": 0}
        return values

    def personal(self, db, owner, card_id):
        row = self.owned(db, "personal_cards", card_id, owner)
        if row["deleted_at"]:
            raise HTTPException(404, "Thẻ đã được xóa khỏi bộ đang học.")
        return row

    def save_card(self, db, owner, body, origin=None, origin_key=None, from_owned_attempt=False):
        if not from_owned_attempt:
            self.refs(db, owner, body.source_refs, body.course_id)
        if origin_key:
            row = db.execute("SELECT id FROM personal_cards WHERE owner_id=? AND origin_key=? AND deleted_at IS NULL", (owner, origin_key)).fetchone()
            if row:
                return {"id": row[0], "reused": True}
        card_id = "personal-" + uuid.uuid4().hex
        db.execute("INSERT INTO personal_cards VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (card_id, owner, body.course_id, body.front, body.back, packed(body.source_refs), packed(origin or {"kind": "manual"}), origin_key, 1, now(), now(), None))
        return {"id": card_id, "version": 1}

    def weak(self, db, owner, course_id):
        course = self.course(db, course_id, owner)
        current = {question_item(course_id, u['id'], i, q)['question_revision_id'] for u in course['content']['units'] if u['unlocked'] and u.get('data') for i, q in enumerate(u['data']['questions'])}
        blocked = {r[0] for r in db.execute("SELECT question_revision_id FROM question_review_flags WHERE course_id=? AND state='needs_review'", (course_id,))}
        latest = {}
        for row in db.execute("SELECT s.items_json,s.course_revision,a.item_id,a.result_json,a.answered_at,s.id AS session_id FROM answers a JOIN study_sessions s ON s.id=a.session_id WHERE s.owner_id=? AND s.course_id=? AND s.status='completed' ORDER BY a.answered_at", (owner, course_id)):
            item = next(q for q in json.loads(row["items_json"]) if q["id"] == row["item_id"])
            original = {k: v for k, v in item.items() if k not in {"id", "unit_id", "question_revision_id", "payload"}}
            unit_id = item.get("unit_id") or item["id"].rsplit(":q", 1)[0]
            key = item.get("question_revision_id") or f"{course_id}:{unit_id}:{content_id(original)}"
            feedback = json.loads(row["result_json"])
            previous = latest.get(key, {"wrong_count": 0})
            latest[key] = {"question": item, "question_revision_id": key, "last_correct": feedback["correct"], "wrong_count": previous["wrong_count"] + (feedback["correct"] is False), "session_id": row["session_id"], "course_revision": row["course_revision"]}
        return [value for value in latest.values() if value["last_correct"] is False and value['question_revision_id'] in current - blocked]

    def update_progress(self, db, owner, course_id, value, expected_version=None):
        previous = db.execute("SELECT version FROM learning_progress WHERE owner_id=? AND course_id=?", (owner, course_id)).fetchone()
        version = previous[0] if previous else 0
        if expected_version is not None and expected_version != version:
            raise HTTPException(409, "Vị trí đã đổi ở phiên khác; tải lại trước khi lưu.")
        db.execute("INSERT INTO learning_progress VALUES (?,?,?,?,?) ON CONFLICT(owner_id,course_id) DO UPDATE SET position_json=excluded.position_json,version=excluded.version,updated_at=excluded.updated_at", (owner, course_id, packed(value), version + 1, now()))
        db.execute("INSERT INTO learning_mode_progress VALUES (?,?,?,?,?) ON CONFLICT(owner_id,course_id,mode) DO UPDATE SET position_json=excluded.position_json,updated_at=excluded.updated_at", (owner, course_id, value["mode"], packed(value), now()))
        return {**value, "version": version + 1}

    def note_value(self, db, owner, note_id):
        row = self.owned(db, "notebook_entries", note_id, owner)
        if db.execute("SELECT 1 FROM notebook_deleted WHERE entry_id=?", (note_id,)).fetchone():
            raise HTTPException(404, "Ghi chú đã được xóa khỏi sổ tay.")
        style = db.execute("SELECT color FROM notebook_styles WHERE entry_id=?", (note_id,)).fetchone()
        return {"id": row["id"], "body": row["body"], "label": row["label"], "source_refs": json.loads(row["refs_json"]), "version": row["version"], "updated_at": row["updated_at"], "color": style[0] if style else None}

    def style_note(self, db, note_id, color):
        db.execute("INSERT INTO notebook_styles VALUES (?,?,?) ON CONFLICT(entry_id) DO UPDATE SET color=excluded.color,updated_at=excluded.updated_at", (note_id, color, now()))


def register_learning(app, store, user, activity=None):
    database = store.database

    @app.get("/api/cards")
    def cards(course_id: str | None = None, only_unremembered: bool = False, owner=Depends(user)):
        with database.connection() as db:
            values = store.cards(db, owner, course_id)
        return [c for c in values if not only_unremembered or c["memory"]["remembered"] is not True]

    @app.post("/api/cards")
    def new_card(body: CardBody, owner=Depends(user)):
        with database.connection(write=True) as db:
            return store.save_card(db, owner, body)

    @app.put("/api/cards/{card_id}")
    def edit_card(card_id: str, body: CardEdit, owner=Depends(user)):
        with database.connection(write=True) as db:
            previous = store.personal(db, owner, card_id)
            if previous["version"] != body.expected_version:
                raise HTTPException(409, "Thẻ đã đổi; không ghi đè bản mới.")
            store.refs(db, owner, body.source_refs, body.course_id)
            db.execute("INSERT INTO personal_card_versions VALUES (?,?,?,?)", (card_id, previous["version"], packed(dict(previous)), now()))
            db.execute("UPDATE personal_cards SET front=?,back=?,course_id=?,refs_json=?,version=version+1,updated_at=? WHERE id=?", (body.front, body.back, body.course_id, packed(body.source_refs), now(), card_id))
            db.execute("DELETE FROM card_memory WHERE owner_id=? AND card_id=?", (owner, card_id))
            return {"id": card_id, "version": previous["version"] + 1}

    @app.delete("/api/cards/{card_id}")
    def delete_card(card_id: str, owner=Depends(user)):
        with database.connection(write=True) as db:
            store.personal(db, owner, card_id)
            db.execute("UPDATE personal_cards SET deleted_at=? WHERE id=?", (now(), card_id))
            return {"id": card_id, "deleted": True, "recoverable": True}

    @app.post("/api/cards/{card_id}/restore")
    def restore_card(card_id: str, owner=Depends(user)):
        with database.connection(write=True) as db:
            row = store.owned(db, "personal_cards", card_id, owner)
            if row["origin_key"] and db.execute("SELECT 1 FROM personal_cards WHERE owner_id=? AND origin_key=? AND deleted_at IS NULL AND id!=?", (owner, row["origin_key"], card_id)).fetchone():
                raise HTTPException(409, "Đã có thẻ đang dùng từ câu này; chưa phục hồi bản trùng.")
            db.execute("UPDATE personal_cards SET deleted_at=NULL WHERE id=?", (card_id,))
            return {"id": card_id, "deleted": False}

    @app.post("/api/cards/from-question")
    def card_from_question(body: FromQuestion, owner=Depends(user)):
        with database.connection(write=True) as db:
            session = store.owned(db, "study_sessions", body.session_id, owner)
            if db.execute("SELECT 1 FROM study_sessions WHERE owner_id=? AND course_id=? AND exam=1 AND status='open'", (owner, session["course_id"])).fetchone():
                raise HTTPException(403, "Nộp lượt kiểm tra trước khi lưu câu/lời giải thành thẻ.")
            item = next((q for q in json.loads(session["items_json"]) if q["id"] == body.item_id), None)
            if not item:
                raise HTTPException(404, "Câu không thuộc lượt của bạn.")
            answer = item["answer"]
            if isinstance(answer, list):
                answer = "\n".join(f"{item['left'][i]} → {item['options'][j]}" if item["kind"] == "matching" else item["options"][j] for i, j in enumerate(answer))
            card = CardBody(front=item["prompt"], back=(str(answer) + "\n\n" + item["explanation"])[:3000], course_id=session["course_id"], source_refs=item["source_refs"])
            key = item.get("question_revision_id") or f"{session['course_id']}:{session['course_revision']}:{item['id']}"
            # The item is copied from this owner's immutable attempt, even if
            # its source is no longer part of the current course. Client text
            # and refs are never accepted on this route.
            return store.save_card(db, owner, card, {"kind": "question", "session_id": body.session_id, "item_id": body.item_id, "course_revision": session["course_revision"]}, key, from_owned_attempt=True)

    @app.put("/api/cards/{card_id}/memory")
    def remember(card_id: str, body: MemoryBody, owner=Depends(user)):
        with database.connection(write=True) as db:
            if body.course_id:
                course = store.course(db, body.course_id, owner)
                if body.expected_revision is not None and body.expected_revision != course["revision"]:
                    raise HTTPException(409, "Khóa đã đổi; xác nhận thẻ ở bản mới.")
            values = store.cards(db, owner, body.course_id)
            selected = next((c for c in values if c['id'] == card_id), None)
            if not selected:
                raise HTTPException(404, "Không có thẻ này trong bộ của bạn.")
            previous = db.execute("SELECT version FROM card_memory WHERE owner_id=? AND card_id=?", (owner, card_id)).fetchone()
            version = previous[0] if previous else 0
            if body.expected_version != version:
                raise HTTPException(409, "Trạng thái thẻ đã đổi ở phiên khác.")
            db.execute("INSERT INTO card_memory VALUES (?,?,?,?,?) ON CONFLICT(owner_id,card_id) DO UPDATE SET remembered=excluded.remembered,version=excluded.version,updated_at=excluded.updated_at", (owner, card_id, int(body.remembered), version + 1, now()))
            rewards = activity.card(db, owner, selected) if activity else []
            return {"card_id": card_id, "remembered": body.remembered, "version": version + 1, "rewards": rewards}

    @app.get("/api/notebook")
    def notebook(owner=Depends(user)):
        with database.connection() as db:
            return [store.note_value(db, owner, r[0]) for r in db.execute("SELECT id FROM notebook_entries WHERE owner_id=? AND id NOT IN (SELECT entry_id FROM notebook_deleted) ORDER BY updated_at DESC", (owner,))]

    @app.post("/api/notebook")
    def new_note(body: NoteBody, owner=Depends(user)):
        with database.connection(write=True) as db:
            store.refs(db, owner, body.source_refs, body.course_id)
            note_id = uuid.uuid4().hex
            db.execute("INSERT INTO notebook_entries VALUES (?,?,?,?,?,?,?,?)", (note_id, owner, body.body, body.label, packed(body.source_refs), now(), now(), 1))
            if body.color:
                store.style_note(db, note_id, body.color)
            return store.note_value(db, owner, note_id)

    @app.put("/api/notebook/{note_id}")
    def edit_note(note_id: str, body: NoteEdit, owner=Depends(user)):
        with database.connection(write=True) as db:
            previous = store.note_value(db, owner, note_id)
            if previous["version"] != body.expected_version:
                raise HTTPException(409, "Ghi chú đã đổi; không ghi đè bản mới.")
            store.refs(db, owner, body.source_refs, body.course_id)
            db.execute("INSERT INTO notebook_versions VALUES (?,?,?,?)", (note_id, previous["version"], packed(previous), now()))
            db.execute("UPDATE notebook_entries SET body=?,label=?,refs_json=?,version=version+1,updated_at=? WHERE id=?", (body.body, body.label, packed(body.source_refs), now(), note_id))
            if body.color:
                store.style_note(db, note_id, body.color)
            return store.note_value(db, owner, note_id)

    @app.put("/api/notebook/{note_id}/color")
    def color_note(note_id: str, body: NoteColorBody, owner=Depends(user)):
        with database.connection(write=True) as db:
            store.note_value(db, owner, note_id)
            store.style_note(db, note_id, body.color)
            return store.note_value(db, owner, note_id)

    @app.delete("/api/notebook/{note_id}")
    def delete_note(note_id: str, owner=Depends(user)):
        with database.connection(write=True) as db:
            store.note_value(db, owner, note_id)
            db.execute("INSERT INTO notebook_deleted VALUES (?,?)", (note_id, now()))
            return {"id": note_id, "deleted": True, "recoverable": True}

    @app.post("/api/notebook/{note_id}/restore")
    def restore_note(note_id: str, owner=Depends(user)):
        with database.connection(write=True) as db:
            store.owned(db, "notebook_entries", note_id, owner)
            db.execute("DELETE FROM notebook_deleted WHERE entry_id=?", (note_id,))
            return store.note_value(db, owner, note_id)

    @app.post("/api/notebook/from-chat")
    def note_from_chat(body: FromChat, owner=Depends(user)):
        with database.connection(write=True) as db:
            message = store.owned(db, "chat_messages", body.message_id, owner)
            if message["role"] != "assistant":
                raise HTTPException(422, "Chọn phản hồi của trợ lý để lưu với nhãn AI.")
            row = db.execute("SELECT entry_id FROM notebook_origins WHERE owner_id=? AND kind='chat' AND origin_id=?", (owner, body.message_id)).fetchone()
            if row:
                return store.note_value(db, owner, row[0])
            note_id = uuid.uuid4().hex
            db.execute("INSERT INTO notebook_entries VALUES (?,?,?,?,?,?,?,?)", (note_id, owner, message["content"], "ai", message["refs_json"], now(), now(), 1))
            db.execute("INSERT INTO notebook_origins VALUES (?,?,?,?,?)", (note_id, owner, "chat", body.message_id, message["revision"]))
            return store.note_value(db, owner, note_id)

    @app.get("/api/courses/{course_id}/progress")
    def progress(course_id: str, owner=Depends(user)):
        with database.connection() as db:
            course = store.course(db, course_id, owner)
            row = db.execute("SELECT * FROM learning_progress WHERE owner_id=? AND course_id=?", (owner, course_id)).fetchone()
            positions = {r["mode"]: json.loads(r["position_json"]) for r in db.execute("SELECT * FROM learning_mode_progress WHERE owner_id=? AND course_id=?", (owner, course_id))}
            return {**json.loads(row["position_json"]), "mode_positions": positions, "version": row["version"], "updated_at": row["updated_at"]} if row else {"version": 0, "mode_positions": positions, "expected_revision": course["revision"], "mode": "learn", "unit_id": course["content"]["units"][0]["id"]}

    @app.put("/api/courses/{course_id}/progress")
    def set_progress(course_id: str, body: ProgressBody, owner=Depends(user)):
        with database.connection(write=True) as db:
            course = store.course(db, course_id, owner)
            if course["revision"] != body.expected_revision:
                raise HTTPException(409, "Lưu vị trí theo bản khóa hiện tại.")
            unit = store.unit(course, body.unit_id)
            if body.mode == "learn" and body.section_index >= len(unit["data"]["sections"] if unit.get("data") else [None]):
                raise HTTPException(422, "Mục đọc không có trong bài.")
            if body.item_id and not body.session_id:
                raise HTTPException(422, "Cần lượt đang làm để lưu đúng câu.")
            if body.session_id:
                session = store.owned(db, "study_sessions", body.session_id, owner)
                if session["course_id"] != course_id or body.item_id and body.item_id not in {q["id"] for q in json.loads(session["items_json"])}:
                    raise HTTPException(422, "Lượt/câu không thuộc khóa này.")
            if body.card_id and body.card_id not in {c["id"] for c in store.cards(db, owner, course_id)}:
                raise HTTPException(422, "Thẻ không thuộc khóa đang học.")
            return store.update_progress(db, owner, course_id, body.model_dump(exclude={"expected_version"}), body.expected_version)

    @app.get("/api/resume")
    def resume(owner=Depends(user)):
        with database.connection() as db:
            values = []
            for row in db.execute("SELECT * FROM learning_progress WHERE owner_id=? ORDER BY updated_at DESC", (owner,)):
                try:
                    course = store.course(db, row["course_id"], owner)
                except HTTPException:
                    continue
                values.append({"course_id": row["course_id"], "title": course["content"]["title"], "position": json.loads(row["position_json"]), "version": row["version"], "updated_at": row["updated_at"]})
            return values

    @app.get("/api/courses/{course_id}/weak-items")
    def weak_items(course_id: str, owner=Depends(user)):
        with database.connection() as db:
            values = store.weak(db, owner, course_id)
            return {"questions": [{**v, "question": public_question(v["question"])} for v in values], "cards": [c for c in store.cards(db, owner, course_id) if c["memory"]["remembered"] is False], "new_learner": not values}
