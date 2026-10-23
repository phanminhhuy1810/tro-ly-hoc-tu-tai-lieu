"""What the AI remembers about one learner in one course.

Every chat and in-lesson help call of a course receives the same small memory:
the learner's own notes ("explain with everyday examples", "I mix up /26 and
/27"), the goal and rules confirmed when the course was planned, the questions
the learner recently got wrong and the overview the AI wrote after reading the
whole approved scope. Notes are per learner; nothing here changes the course.
The learner's tutor style ("be a patient tutor", "always stress the formulas")
is set once in Cài đặt and joins the memory of every course.
"""
import json
from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from pydantic import Field

from .models import Model

MAX_NOTES = 1500
MAX_STYLE = 300
MAX_STRUGGLES = 5
MEMORY_RULE = ('course_memory là ghi nhớ của khóa: ghi chú người học tự viết, mục tiêu/quy tắc khi tạo khóa, các câu gần đây làm sai và tổng quan khóa. '
               'Dùng nó để điều chỉnh cách giải thích (ví dụ nhắc lại chỗ hay nhầm, theo cách học người học muốn); '
               'không coi là nguồn kiến thức và không ghi nó vào source_refs. '
               'tutor_style (nếu có) là vai và điều người học muốn được nhấn mạnh: nói theo vai đó và nhấn mạnh điều đó, '
               'nhưng kiến thức nói là của bài vẫn phải dựa trên nguồn và giữ mọi quy tắc ở trên. ')


class MemoryEdit(Model):
    notes: str = Field(max_length=MAX_NOTES)
    expected_version: int = Field(ge=0)


class TutorStyleEdit(Model):
    persona: str = Field(max_length=MAX_STYLE)
    emphasis: str = Field(max_length=MAX_STYLE)
    expected_version: int = Field(ge=0)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def saved_notes(db, owner, course_id):
    row = db.execute('SELECT notes,version,updated_at FROM course_memory WHERE owner_id=? AND course_id=?', (owner, course_id)).fetchone()
    return {'notes': row['notes'], 'version': row['version'], 'updated_at': row['updated_at']} if row else {'notes': '', 'version': 0, 'updated_at': None}


def tutor_style(db, owner):
    row = db.execute('SELECT persona,emphasis,version,updated_at FROM tutor_styles WHERE owner_id=?', (owner,)).fetchone()
    return dict(row) if row else {'persona': '', 'emphasis': '', 'version': 0, 'updated_at': None}


def struggles(db, owner, course_id, limit=MAX_STRUGGLES):
    """Questions recently answered wrong in this course, newest first, one entry per question."""
    seen, found, sessions = set(), [], {}
    rows = db.execute('''SELECT a.session_id, a.item_id, a.result_json FROM answers a JOIN study_sessions s ON s.id=a.session_id
                         WHERE s.owner_id=? AND s.course_id=? ORDER BY a.answered_at DESC LIMIT 80''', (owner, course_id)).fetchall()
    for row in rows:
        if json.loads(row['result_json']).get('correct') is not False:
            continue
        if row['session_id'] not in sessions:
            items = db.execute('SELECT items_json FROM study_sessions WHERE id=?', (row['session_id'],)).fetchone()[0]
            sessions[row['session_id']] = {q['id']: q for q in json.loads(items)}
        item = sessions[row['session_id']].get(row['item_id'])
        key = item and (item.get('question_revision_id') or item['prompt'])
        if not item or key in seen:
            continue
        seen.add(key)
        found.append({'prompt': ' '.join(item['prompt'].split())[:220], 'unit_id': item.get('unit_id')})
        if len(found) >= limit:
            break
    return found


def memory_for_ai(db, owner, course, overview=None):
    """Compact memory for an AI instruction, or None when there is nothing to remember yet."""
    prefs = course['content'].get('preferences') or {}
    value = {
        'learner_notes': saved_notes(db, owner, course['id'])['notes'].strip() or None,
        'course_goal': prefs.get('goal') or None,
        'course_rules': (prefs.get('instructions') or '').strip()[:600] or None,
        'terms_to_keep': prefs.get('terms_to_keep') or None,
        'recent_mistakes': [s['prompt'] for s in struggles(db, owner, course['id'])] or None,
        'course_overview': overview,
        'tutor_style': {k: v for k, v in tutor_style(db, owner).items() if k in ('persona', 'emphasis') and v} or None,
    }
    value = {k: v for k, v in value.items() if v}
    return value or None


def register_course_memory(app, database, course_snapshot, user, overview):
    @app.get('/api/courses/{course_id}/memory')
    def read_memory(course_id: str, owner=Depends(user)):
        with database.connection() as db:
            course = course_snapshot(db, course_id, owner)
            prefs = course['content'].get('preferences') or {}
            keys = ('subject', 'goal', 'language') if course.get('access_role') == 'learner' else (
                'subject', 'goal', 'instructions', 'language', 'terms_to_keep', 'chapter_priorities')
            return {**saved_notes(db, owner, course_id), 'max_notes': MAX_NOTES,
                    'struggles': struggles(db, owner, course_id),
                    'course': {k: prefs.get(k) for k in keys},
                    'overview': overview(db, owner, course)}

    @app.get('/api/tutor-style')
    def read_style(owner=Depends(user)):
        with database.connection() as db:
            return {**tutor_style(db, owner), 'max_length': MAX_STYLE}

    @app.put('/api/tutor-style')
    def write_style(body: TutorStyleEdit, owner=Depends(user)):
        with database.connection(write=True) as db:
            current = tutor_style(db, owner)
            if current['version'] != body.expected_version:
                raise HTTPException(409, 'Phong cách của Byte vừa được sửa ở cửa sổ khác; tải lại trước khi lưu.')
            db.execute('INSERT INTO tutor_styles VALUES (?,?,?,?,?) ON CONFLICT(owner_id) DO UPDATE SET '
                       'persona=excluded.persona,emphasis=excluded.emphasis,version=excluded.version,updated_at=excluded.updated_at',
                       (owner, body.persona.strip(), body.emphasis.strip(), current['version'] + 1, stamp()))
            return {**tutor_style(db, owner), 'max_length': MAX_STYLE}

    @app.put('/api/courses/{course_id}/memory')
    def write_memory(course_id: str, body: MemoryEdit, owner=Depends(user)):
        with database.connection(write=True) as db:
            course_snapshot(db, course_id, owner)
            current = saved_notes(db, owner, course_id)
            if current['version'] != body.expected_version:
                raise HTTPException(409, 'Ghi nhớ vừa được sửa ở cửa sổ khác; tải lại trước khi lưu.')
            db.execute('INSERT INTO course_memory VALUES (?,?,?,?,?) ON CONFLICT(owner_id,course_id) DO UPDATE SET '
                       'notes=excluded.notes,version=excluded.version,updated_at=excluded.updated_at',
                       (owner, course_id, body.notes.strip(), current['version'] + 1, stamp()))
            return saved_notes(db, owner, course_id)
