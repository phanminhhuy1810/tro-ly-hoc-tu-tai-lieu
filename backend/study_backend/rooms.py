"""Version-pinned, deterministic quiz rooms over authenticated HTTP and SSE."""
import asyncio
import hashlib
import json
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask
from pydantic import Field, StrictInt, StrictStr

from .learning import grade_answer, normalized_answer, public_question, question_item
from .models import ChatReply, Model, Question
from .language import language_instruction, validate_language
from .ordering import verify_ordering
from .question_quality import verify_mcq_options


POLICY = {'version': 'room-proposal-20261017-v1', 'proposed': True, 'max_players': 8,
          'max_questions': 20, 'host_grace_seconds': 60, 'member_presence_seconds': 45,
          'reveal_seconds': 8, 'room_ttl_seconds': 1800, 'join_attempts_per_minute': 20,
          'points_per_correct': 1, 'speed_bonus': False, 'coin_reward': 0,
          'host_leave': 'cancel_room', 'late_answer': 'reject', 'ai_help': 'after_room_only',
          'room_does_not_unlock_personal_units': True, 'not_a_proctored_exam': True}
ACTIVE = {'lobby', 'question_open', 'question_closed'}
TERMINAL = {'finished', 'cancelled'}


def dump(value): return json.dumps(value, ensure_ascii=False, sort_keys=True)
def uid(): return uuid.uuid4().hex
def iso(value): return datetime.fromtimestamp(value, timezone.utc).isoformat() if value is not None else None


class CreateRoom(Model):
    course_id: str
    expected_revision: int = Field(ge=1)
    unit_ids: list[str] = Field(min_length=1, max_length=30)
    question_count: int = Field(default=5, ge=1, le=20)
    seconds_per_question: int = Field(default=30, ge=5, le=180)
    nickname: str = Field(min_length=1, max_length=40)


class JoinRoom(Model):
    code: str = Field(min_length=6, max_length=10)
    nickname: str = Field(min_length=1, max_length=40)


class RoomAction(Model):
    expected_event_index: int = Field(ge=1)


class RoomAnswer(Model):
    event_index: int = Field(ge=1)
    question_id: str = Field(min_length=1, max_length=200)
    answer: str | list[StrictInt] | list[StrictStr] | dict[str, StrictStr]


class RoomHelp(Model):
    question_id: str
    message: str = Field(min_length=1, max_length=2000)


class RoomStore:
    def __init__(self, database, clock=None, policy=None):
        self.database = database
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.policy = {**POLICY, **(policy or {})}
        if any(not isinstance(self.policy[k], int) or self.policy[k] <= 0 for k in
               ['max_players', 'max_questions', 'host_grace_seconds', 'member_presence_seconds',
                'reveal_seconds', 'room_ttl_seconds', 'join_attempts_per_minute']):
            raise ValueError('Room policy needs positive bounded timing/capacity limits.')
        if self.policy['max_players'] > 20 or self.policy['max_questions'] > 20 or self.policy['room_ttl_seconds'] > 7200:
            raise ValueError('Room trial capacity exceeded.')
        if self.policy['host_leave'] != 'cancel_room' or self.policy['speed_bonus'] or self.policy['coin_reward'] != 0 or not 1 <= self.policy['points_per_correct'] <= 10:
            raise ValueError('Unsupported room policy; no speed bonus, transfer or Coin rule is implemented.')
        self.streams = {}

    def now(self): return self.clock().timestamp()

    def room(self, db, room_id):
        row = db.execute('SELECT * FROM quiz_rooms WHERE id=?', (room_id,)).fetchone()
        if not row: raise HTTPException(404, 'Không có phòng này trong phiên của bạn.')
        return dict(row)

    def member(self, db, room_id, actor):
        row = db.execute('SELECT * FROM quiz_members WHERE room_id=? AND user_id=?', (room_id, actor)).fetchone()
        if not row: raise HTTPException(404, 'Vào phòng bằng mã trước khi xem nội dung.')
        return dict(row)

    def event(self, db, room, kind, data=None):
        room['event_index'] += 1
        room['updated_at'] = self.now()
        db.execute('UPDATE quiz_rooms SET phase=?,current_index=?,closed_count=?,event_index=?,question_event_index=?,deadline=?,updated_at=?,end_reason=? WHERE id=?',
                   (room['phase'], room['current_index'], room['closed_count'], room['event_index'], room['question_event_index'], room['deadline'], room['updated_at'], room['end_reason'], room['id']))
        db.execute('INSERT INTO quiz_events VALUES (?,?,?,?,?)', (room['id'], room['event_index'], kind, dump(data or {}), room['updated_at']))

    def cancel(self, db, room, reason):
        if room['phase'] in TERMINAL: return
        room.update(phase='cancelled', deadline=None, end_reason=reason)
        self.event(db, room, 'cancelled', {'reason': reason})

    def open_question(self, db, room, at):
        bank = json.loads(room['bank_json'])
        if room['current_index'] + 1 >= len(bank):
            room.update(phase='finished', deadline=None, end_reason='all_questions_closed')
            self.event(db, room, 'finished')
        else:
            candidate = bank[room['current_index'] + 1]
            if self.warning(db, room, candidate):
                self.cancel(db, room, 'question_needs_review'); return
            room.update(phase='question_open', current_index=room['current_index'] + 1,
                        deadline=at + json.loads(room['settings_json'])['seconds_per_question'],
                        question_event_index=room['event_index'] + 1)
            self.event(db, room, 'question_open', {'question_index': room['current_index'], 'deadline': iso(room['deadline'])})

    def close_question(self, db, room, at, reason):
        if room['phase'] != 'question_open': return
        room.update(phase='question_closed', closed_count=room['current_index'] + 1,
                    deadline=at + json.loads(room['settings_json'])['policy']['reveal_seconds'])
        self.event(db, room, 'question_closed', {'question_index': room['current_index'], 'reason': reason})

    def advance(self, db, room):
        now = self.now()
        settings = json.loads(room['settings_json'])
        for _ in range(2 * len(json.loads(room['bank_json'])) + 4):
            if room['phase'] in TERMINAL: break
            if now >= room['expires_at']:
                self.cancel(db, room, 'room_expired'); break
            if now >= room['host_seen_at'] + settings['policy']['host_grace_seconds']:
                self.cancel(db, room, 'host_disconnected'); break
            if room['phase'] == 'question_open' and self.warning(db, room, json.loads(room['bank_json'])[room['current_index']]):
                self.cancel(db, room, 'question_needs_review'); break
            if room['phase'] == 'question_open' and now >= room['deadline']:
                self.close_question(db, room, room['deadline'], 'deadline'); continue
            if room['phase'] == 'question_closed' and now >= room['deadline']:
                self.open_question(db, room, room['deadline']); continue
            break
        return room

    def warning(self, db, room, question):
        row = db.execute("SELECT reason FROM question_review_flags WHERE course_id=? AND question_revision_id=? AND state='needs_review'", (room['course_id'], question['question_revision_id'])).fetchone()
        return row['reason'] if row else None

    def tick(self):
        with self.database.connection(write=True) as db:
            for row in db.execute("SELECT * FROM quiz_rooms WHERE phase IN ('lobby','question_open','question_closed') ORDER BY updated_at LIMIT 200").fetchall():
                self.advance(db, dict(row))

    def active(self, db, actor, course_id=None):
        rows = db.execute("SELECT r.* FROM quiz_rooms r JOIN quiz_members m ON m.room_id=r.id WHERE m.user_id=? AND m.state='joined' AND r.phase IN ('question_open','question_closed')" + (' AND r.course_id=?' if course_id else ''), (actor, course_id) if course_id else (actor,)).fetchall()
        now = self.now()
        return any(now < r['expires_at'] and now < r['host_seen_at'] + json.loads(r['settings_json'])['policy']['host_grace_seconds'] for r in rows)

    def ensure_free(self, db, actor, except_room=None):
        for row in db.execute("SELECT r.* FROM quiz_rooms r JOIN quiz_members m ON m.room_id=r.id WHERE m.user_id=? AND m.state='joined' AND r.phase IN ('lobby','question_open','question_closed')", (actor,)).fetchall():
            room = self.advance(db, dict(row))
            if room['phase'] in ACTIVE and room['id'] != except_room:
                raise HTTPException(409, 'Rời hoặc kết thúc phòng cũ trước khi vào phòng khác.')

    def touch(self, db, room, member):
        if room['phase'] not in ACTIVE or member['state'] != 'joined': return
        at = self.now()
        db.execute('UPDATE quiz_members SET last_seen_at=? WHERE room_id=? AND user_id=?', (at, room['id'], member['user_id']))
        if member['user_id'] == room['creator_id']:
            room['host_seen_at'] = at
            db.execute('UPDATE quiz_rooms SET host_seen_at=? WHERE id=?', (at, room['id']))

    def scoreboard(self, db, room):
        values = []
        for member in db.execute('SELECT * FROM quiz_members WHERE room_id=? ORDER BY joined_at,id', (room['id'],)):
            score = db.execute('SELECT coalesce(sum(points),0),count(*) FROM quiz_answers WHERE room_id=? AND user_id=? AND question_index<?', (room['id'], member['user_id'], room['closed_count'])).fetchone()
            values.append({'member_id': member['id'], 'nickname': member['nickname'], 'state': member['state'],
                           'is_host': member['user_id'] == room['creator_id'], 'score': score[0], 'answered_closed_questions': score[1],
                           'connected': room['phase'] in ACTIVE and member['state'] == 'joined' and self.now() - member['last_seen_at'] < json.loads(room['settings_json'])['policy']['member_presence_seconds']})
        values.sort(key=lambda value: (-value['score'], value['nickname'].casefold(), value['member_id']))
        previous = None
        for i, value in enumerate(values):
            value['rank'] = previous['rank'] if previous and previous['score'] == value['score'] else i + 1
            previous = value
        return values

    def snapshot(self, db, room, member):
        bank = json.loads(room['bank_json'])
        settings = json.loads(room['settings_json'])
        current = bank[room['current_index']] if room['current_index'] >= 0 else None
        value = {'id': room['id'], 'course_revision': room['course_revision'], 'title': settings['title'],
                 'phase': room['phase'], 'event_index': room['event_index'], 'question_index': room['current_index'],
                 'question_event_index': room['question_event_index'], 'seconds_per_question': settings['seconds_per_question'],
                 'question_count': len(bank), 'closed_count': room['closed_count'], 'deadline': iso(room['deadline']),
                 'server_time': iso(self.now()), 'expires_at': iso(room['expires_at']), 'end_reason': room['end_reason'],
                 'policy': settings['policy'], 'scoreboard': self.scoreboard(db, room),
                 'me': {'member_id': member['id'], 'state': member['state'], 'is_host': member['user_id'] == room['creator_id']},
                 'question': None, 'own_answer': None, 'own_result': None, 'solution': None, 'reference_warning': self.warning(db, room, current) if current else None,
                 'ai_help_available': room['phase'] in TERMINAL and room['closed_count'] > 0}
        if current and (member['state'] == 'joined' or room['current_index'] < room['closed_count']):
            value['question'] = public_question(current)
            answer = db.execute('SELECT answer_json,correct,points FROM quiz_answers WHERE room_id=? AND user_id=? AND question_index=?', (room['id'], member['user_id'], room['current_index'])).fetchone()
            value['own_answer'] = json.loads(answer['answer_json']) if answer else None
            if room['current_index'] < room['closed_count']:
                value['solution'] = {k: current[k] for k in ['answer', 'explanation', 'source_refs']}
                # Correctness only once the question is closed, like the solution itself.
                if answer: value['own_result'] = {'correct': bool(answer['correct']), 'points': answer['points']}
        return value

    def intent(self, db, actor, request, operation, payload):
        key = request.headers.get('Idempotency-Key')
        if not key or not key.strip() or len(key) > 128:
            raise HTTPException(422, 'Thao tác phòng cần Idempotency-Key 1–128 ký tự.')
        digest = hashlib.sha256(dump(payload).encode()).hexdigest()
        row = db.execute('SELECT digest,result_json FROM idempotency WHERE owner_id=? AND operation=? AND request_key=?', (actor, operation, key)).fetchone()
        if row and row['digest'] != digest: raise HTTPException(409, 'Intent đã dùng cho nội dung khác; chưa ghi đè thao tác phòng.')
        return (key, digest), json.loads(row['result_json']) if row else None

    def remember(self, db, actor, operation, identity, result):
        db.execute('INSERT INTO idempotency VALUES (?,?,?,?,?,?)', (actor, operation, *identity, dump(result), iso(self.now())))


def register_rooms(app, rooms, database, user, course_snapshot, course_plan, approved_fragments,
                   unit_from, owned, active_test, jobs, generate_checked):
    def host_course(db, course_id, actor):
        course = course_snapshot(db, course_id, actor)
        if course['creator_id'] != actor:
            publication = db.execute('SELECT visibility FROM course_publications WHERE course_id=?', (course_id,)).fetchone()
            if not publication or publication[0] != 'public':
                raise HTTPException(403, 'Khóa chia sẻ riêng chỉ người tạo được đưa vào phòng; học viên có thể dùng khóa công khai đã tham gia.')
        return course

    def bank_for(db, course, owner, unit_ids):
        bank, sources, omitted = [], {}, []
        flagged = {r[0] for r in db.execute("SELECT question_revision_id FROM question_review_flags WHERE course_id=? AND state='needs_review'", (course['id'],))}
        for unit_id in unit_ids:
            unit = unit_from(course, unit_id, ready=True)
            plan = course_plan(db, course, owner, unit)
            fragments = approved_fragments(db, plan, course['creator_id'], unit['source_refs'])
            sources.update({f['id']: f for f in fragments})
            for index, question in enumerate(unit['data']['questions']):
                item = question_item(course['id'], unit_id, index, question)
                try:
                    if question['kind'] == 'short_answer': raise ValueError('Tự luận vẫn ở học/ôn cá nhân; room thử chỉ dùng câu chấm cố định.')
                    if item['question_revision_id'] in flagged: raise ValueError('Câu đã được đánh dấu cần xem lại.')
                    Question.model_validate(question); verify_mcq_options(question); verify_ordering(question, fragments)
                    if any(ref not in {f['id'] for f in fragments} for ref in question['source_refs']): raise ValueError('Câu không khớp nguồn đã duyệt của bài.')
                except ValueError as exc:
                    omitted.append({'question_id': item['id'], 'reason': str(exc)}); continue
                item['content_language'] = json.loads(plan['preferences_json']).get('language', 'source')
                bank.append(item)
        return bank, sources, omitted

    @app.get('/api/courses/{course_id}/room-bank')
    def bank_preview(course_id: str, expected_revision: int, unit_ids: str = '', owner=Depends(user)):
        with database.connection() as db:
            course = host_course(db, course_id, owner)
            if course['revision'] != expected_revision:
                raise HTTPException(409, 'Khóa đã đổi; tải lại trước khi chọn bộ câu.')
            scope = [x.strip() for x in unit_ids.split(',') if x.strip()] if unit_ids else [u['id'] for u in course['content']['units'] if u['unlocked'] and u.get('data')]
            if len(scope) > 30 or len(set(scope)) != len(scope):
                raise HTTPException(422, 'Phạm vi bài không hợp lệ hoặc bị lặp.')
            bank, _, omitted = bank_for(db, course, owner, scope)
            return {'course_id': course_id, 'revision': course['revision'], 'unit_ids': scope,
                    'units': [{'id': u['id'], 'title': u['title'], 'unlocked': u['unlocked'], 'generated': bool(u.get('data'))} for u in course['content']['units']],
                    'available': len(bank), 'max_selectable': min(len(bank), rooms.policy['max_questions']),
                    'questions': [public_question(q) for q in bank], 'omitted': omitted, 'policy': dict(rooms.policy),
                    'sharing': 'Người vào bằng mã được xem câu/trích nguồn đã chọn, không được mở cả khóa hoặc file gốc.'}

    @app.post('/api/rooms')
    def create(body: CreateRoom, request: Request, owner=Depends(user)):
        if not body.nickname.strip() or len(set(body.unit_ids)) != len(body.unit_ids):
            raise HTTPException(422, 'Nhập tên và phạm vi bài không lặp.')
        with database.connection(write=True) as db:
            identity, prior = rooms.intent(db, owner, request, 'room:create', body.model_dump())
            if prior: return {**prior, 'join_code_not_replayed': True}
            rooms.ensure_free(db, owner)
            if active_test(db, owner, body.course_id): raise HTTPException(403, 'Kết thúc lượt kiểm tra trước khi tạo phòng.')
            course = host_course(db, body.course_id, owner)
            if course['revision'] != body.expected_revision: raise HTTPException(409, 'Khóa đã đổi; chọn lại bộ câu trước khi tạo phòng.')
            bank, sources, omitted = bank_for(db, course, owner, body.unit_ids)
            if body.question_count > min(len(bank), rooms.policy['max_questions']):
                raise HTTPException(422, {'message': 'Chưa đủ câu cố định hợp lệ; giảm số câu hoặc xem lại bank. Không gọi AI/lặp câu để đủ số.', 'available': len(bank), 'omitted': omitted})
            bank = bank[:body.question_count]
            refs = {ref for item in bank for ref in item['source_refs']}
            room_id, at = uid(), rooms.now()
            code = ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(8))
            settings = {'title': course['content']['title'], 'seconds_per_question': body.seconds_per_question, 'policy': dict(rooms.policy)}
            db.execute('INSERT INTO quiz_rooms (id,creator_id,course_id,course_revision,code_hash,settings_json,bank_json,sources_json,phase,current_index,closed_count,event_index,deadline,created_at,updated_at,expires_at,host_seen_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (room_id, owner, course['id'], course['revision'], hashlib.sha256(code.encode()).hexdigest(), dump(settings), dump(bank), dump({k: sources[k] for k in refs}), 'lobby', -1, 0, 1, None, at, at, at + rooms.policy['room_ttl_seconds'], at,))
            # end_reason is nullable and supplied by the schema default.
            member_id = uid()
            db.execute('INSERT INTO quiz_members VALUES (?,?,?,?,?,?,?)', (member_id, room_id, owner, body.nickname.strip(), 'joined', at, at))
            db.execute('INSERT INTO quiz_events VALUES (?,?,?,?,?)', (room_id, 1, 'created', '{}', at))
            result = {'room_id': room_id, 'phase': 'lobby', 'event_index': 1, 'policy': settings['policy'], 'question_count': len(bank), 'omitted': omitted}
            rooms.remember(db, owner, 'room:create', identity, result)
            return {**result, 'join_code': code, 'join_path': '/?room_code=' + code + '#rooms',
                    'sharing': 'Mã cho phép vào bộ câu/trích nguồn đã chọn; không enroll cả khóa hoặc mở file gốc.'}

    @app.post('/api/rooms/join')
    def join(body: JoinRoom, owner=Depends(user)):
        nickname, code = body.nickname.strip(), body.code.strip().upper()
        if not nickname: raise HTTPException(422, 'Nhập tên hiển thị trong phòng.')
        with database.connection(write=True) as db:
            at = rooms.now()
            row = db.execute('SELECT * FROM quiz_join_attempts WHERE owner_id=?', (owner,)).fetchone()
            count = row['attempts'] + 1 if row and at - row['window_start'] < 60 else 1
            start = row['window_start'] if row and at - row['window_start'] < 60 else at
            db.execute('INSERT INTO quiz_join_attempts VALUES (?,?,?) ON CONFLICT(owner_id) DO UPDATE SET window_start=excluded.window_start,attempts=excluded.attempts', (owner, start, count))
            if count > rooms.policy['join_attempts_per_minute']:
                return JSONResponse(status_code=429, content={'detail': 'Thử mã quá nhiều; chờ một phút rồi thử lại.'})
            row = db.execute('SELECT * FROM quiz_rooms WHERE code_hash=?', (hashlib.sha256(code.encode()).hexdigest(),)).fetchone()
            if not row: return JSONResponse(status_code=404, content={'detail': 'Mã phòng không còn hiệu lực.'})
            room = rooms.advance(db, dict(row))
            existing = db.execute('SELECT * FROM quiz_members WHERE room_id=? AND user_id=?', (room['id'], owner)).fetchone()
            if existing and existing['state'] == 'joined' and room['phase'] in ACTIVE:
                rooms.touch(db, room, dict(existing)); return rooms.snapshot(db, room, dict(existing))
            if room['phase'] != 'lobby': return JSONResponse(status_code=409, content={'detail': 'Phòng đã bắt đầu hoặc kết thúc; chưa thêm người vào giữa lượt.'})
            rooms.ensure_free(db, owner, room['id'])
            members = db.execute("SELECT * FROM quiz_members WHERE room_id=? AND state='joined'", (room['id'],)).fetchall()
            if len(members) >= json.loads(room['settings_json'])['policy']['max_players']: raise HTTPException(409, 'Phòng đã đủ người.')
            if any(m['nickname'].casefold() == nickname.casefold() and m['user_id'] != owner for m in members): raise HTTPException(409, 'Tên hiển thị đã có trong phòng; chọn tên khác.')
            db.execute("INSERT INTO quiz_members VALUES (?,?,?,?,?,?,?) ON CONFLICT(room_id,user_id) DO UPDATE SET state='joined',nickname=excluded.nickname,last_seen_at=excluded.last_seen_at", (uid(), room['id'], owner, nickname, 'joined', at, at))
            rooms.event(db, room, 'member_joined')
            return rooms.snapshot(db, room, rooms.member(db, room['id'], owner))

    @app.get('/api/rooms')
    def listing(owner=Depends(user)):
        with database.connection(write=True) as db:
            values = []
            for row in db.execute('SELECT r.* FROM quiz_rooms r JOIN quiz_members m ON m.room_id=r.id WHERE m.user_id=? ORDER BY r.created_at DESC LIMIT 100', (owner,)).fetchall():
                room = rooms.advance(db, dict(row))
                values.append({'id': room['id'], 'phase': room['phase'], 'event_index': room['event_index'], 'title': json.loads(room['settings_json'])['title'], 'created_at': iso(room['created_at'])})
            return values

    def view(room_id, actor, touch=True):
        with database.connection(write=True) as db:
            room, member = rooms.room(db, room_id), rooms.member(db, room_id, actor)
            room = rooms.advance(db, room)
            if room['phase'] in TERMINAL and active_test(db, actor, room['course_id']):
                raise HTTPException(403, 'Mở lại kết quả cũ sau phòng/lượt kiểm tra đang tính điểm.')
            if touch: rooms.touch(db, room, member)
            return rooms.snapshot(db, room, member)

    @app.get('/api/rooms/{room_id}')
    def snapshot(room_id: str, owner=Depends(user)):
        return view(room_id, owner)

    @app.post('/api/rooms/{room_id}/presence')
    def presence(room_id: str, owner=Depends(user)):
        return view(room_id, owner)

    def control(room_id: str, action: str, body: RoomAction, request: Request, owner=Depends(user)):
        if action not in {'start', 'next', 'close-question', 'close', 'leave', 'invite'}: raise HTTPException(404, 'Không có thao tác phòng này.')
        with database.connection(write=True) as db:
            room, member = rooms.room(db, room_id), rooms.member(db, room_id, owner)
            identity, prior = rooms.intent(db, owner, request, 'room:' + room_id + ':' + action, body.model_dump())
            if prior: return prior
            room = rooms.advance(db, room)
            if room['event_index'] != body.expected_event_index: return JSONResponse(status_code=409, content={'detail': 'Phòng đã đổi; lấy snapshot mới trước thao tác.', 'event_index': room['event_index']})
            if member['state'] != 'joined' or room['phase'] in TERMINAL: return JSONResponse(status_code=409, content={'detail': 'Bạn đã rời hoặc phòng đã kết thúc.'})
            if action != 'leave' and owner != room['creator_id']: raise HTTPException(403, 'Chỉ chủ phòng được điều khiển lượt.')
            rooms.touch(db, room, member)
            extra = {}
            if action == 'start':
                if room['phase'] != 'lobby': raise HTTPException(409, 'Phòng đã bắt đầu.')
                online = db.execute("SELECT count(*) FROM quiz_members WHERE room_id=? AND state='joined' AND last_seen_at>?", (room_id, rooms.now() - json.loads(room['settings_json'])['policy']['member_presence_seconds'])).fetchone()[0]
                if online < 2: raise HTTPException(409, 'Cần ít nhất hai phiên kết nối để bắt đầu.')
                if any(active_test(db, row['user_id'], room['course_id']) for row in db.execute("SELECT user_id FROM quiz_members WHERE room_id=? AND state='joined'", (room_id,))):
                    raise HTTPException(403, 'Một người trong phòng đang kiểm tra; kết thúc lượt đó hoặc rời phòng trước khi bắt đầu.')
                rooms.open_question(db, room, rooms.now())
            elif action == 'close-question':
                if room['phase'] != 'question_open': raise HTTPException(409, 'Câu hiện tại đã đóng.')
                rooms.close_question(db, room, rooms.now(), 'host_closed')
            elif action == 'next':
                if room['phase'] != 'question_closed': raise HTTPException(409, 'Đóng câu hiện tại trước khi sang câu tiếp.')
                rooms.open_question(db, room, rooms.now())
            elif action == 'close': rooms.cancel(db, room, 'host_closed_room')
            elif action == 'leave':
                db.execute("UPDATE quiz_members SET state='left' WHERE room_id=? AND user_id=?", (room_id, owner))
                if owner == room['creator_id']: rooms.cancel(db, room, 'host_left')
                else: rooms.event(db, room, 'member_left')
            elif action == 'invite':
                if room['phase'] != 'lobby': raise HTTPException(409, 'Chỉ đổi mã trong sảnh chờ.')
                code = ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(8))
                db.execute('UPDATE quiz_rooms SET code_hash=? WHERE id=?', (hashlib.sha256(code.encode()).hexdigest(), room_id))
                rooms.event(db, room, 'invite_rotated'); extra['join_code'] = code
            result = {'room_id': room_id, 'phase': room['phase'], 'event_index': room['event_index']}
            rooms.remember(db, owner, 'room:' + room_id + ':' + action, identity, result)
            return {**result, **extra}

    @app.post('/api/rooms/{room_id}/answers')
    def answer(room_id: str, body: RoomAnswer, request: Request, owner=Depends(user)):
        with database.connection(write=True) as db:
            room, member = rooms.room(db, room_id), rooms.member(db, room_id, owner)
            identity, prior = rooms.intent(db, owner, request, 'room:' + room_id + ':answer', body.model_dump())
            if prior: return prior
            bank = json.loads(room['bank_json'])
            index = next((i for i,q in enumerate(bank) if q['id'] == body.question_id), None)
            if index is None: raise HTTPException(422, 'Câu không thuộc bộ đã chốt của phòng.')
            existing = db.execute('SELECT answer_json,received_at FROM quiz_answers WHERE room_id=? AND user_id=? AND question_index=?', (room_id, owner, index)).fetchone()
            if existing:
                if json.loads(existing['answer_json']) != body.answer: raise HTTPException(409, 'Câu đã nhận đáp án; không sửa bằng một intent khác.')
                result = {'accepted': True, 'question_id': body.question_id, 'received_at': iso(existing['received_at']), 'replayed': True}
                rooms.remember(db, owner, 'room:' + room_id + ':answer', identity, result); return result
            room = rooms.advance(db, room)
            if member['state'] != 'joined' or room['phase'] != 'question_open' or room['current_index'] != index or room['question_event_index'] != body.event_index:
                return JSONResponse(status_code=409, content={'detail': 'Câu đã đóng/đổi hoặc bạn đã rời; chưa nhận đáp án mới.'})
            if rooms.now() >= room['deadline']:
                return JSONResponse(status_code=409, content={'detail': 'Đã hết thời hạn server; chưa nhận đáp án.'})
            try: graded = grade_answer(bank[index], body.answer)
            except ValueError as exc: raise HTTPException(422, str(exc)) from exc
            at = rooms.now(); rooms.touch(db, room, member)
            points = int(bool(graded['correct'])) * json.loads(room['settings_json'])['policy']['points_per_correct']
            db.execute('INSERT INTO quiz_answers VALUES (?,?,?,?,?,?,?,?)', (room_id, owner, index, dump(body.answer), int(graded['correct']), points, at, body.event_index))
            result = {'accepted': True, 'question_id': body.question_id, 'received_at': iso(at)}
            rooms.remember(db, owner, 'room:' + room_id + ':answer', identity, result)
            remaining = db.execute("SELECT count(*) FROM quiz_members m WHERE m.room_id=? AND m.state='joined' AND NOT EXISTS (SELECT 1 FROM quiz_answers a WHERE a.room_id=m.room_id AND a.user_id=m.user_id AND a.question_index=?)", (room_id, index)).fetchone()[0]
            if remaining == 0: rooms.close_question(db, room, at, 'all_answered')
            return result

    @app.get('/api/rooms/{room_id}/results')
    def results(room_id: str, owner=Depends(user)):
        with database.connection(write=True) as db:
            room, member = rooms.room(db, room_id), rooms.member(db, room_id, owner)
            room = rooms.advance(db, room)
            if room['phase'] not in TERMINAL: return JSONResponse(status_code=409, content={'detail': 'Xem tổng kết khi phòng kết thúc.'})
            if active_test(db, owner, room['course_id']): raise HTTPException(403, 'Mở kết quả cũ sau lượt đang tính điểm của khóa này.')
            bank, sources = json.loads(room['bank_json']), json.loads(room['sources_json'])
            questions = []
            for index, question in enumerate(bank[:room['closed_count']]):
                own = db.execute('SELECT * FROM quiz_answers WHERE room_id=? AND user_id=? AND question_index=?', (room_id, owner, index)).fetchone()
                questions.append({**public_question(question), 'solution': {k: question[k] for k in ['answer','explanation','source_refs']},
                                  'sources': [sources[ref] for ref in question['source_refs']],
                                  'reference_warning': rooms.warning(db, room, question),
                                  'own_answer': json.loads(own['answer_json']) if own else None, 'correct': bool(own['correct']) if own else False, 'points': own['points'] if own else 0})
            return {'room_id': room_id, 'phase': room['phase'], 'course_revision': room['course_revision'], 'scoreboard': rooms.scoreboard(db, room), 'questions': questions, 'policy': json.loads(room['settings_json'])['policy'], 'end_reason': room['end_reason']}

    @app.get('/api/rooms/{room_id}/events')
    async def events(room_id: str, request: Request, once: bool = False, owner=Depends(user)):
        initial = view(room_id, owner)
        try: cursor = int(request.headers.get('Last-Event-ID', '0'))
        except ValueError: raise HTTPException(422, 'Last-Event-ID cần là số nguyên.') from None
        if not 0 <= cursor <= initial['event_index']: raise HTTPException(409, 'Cursor không thuộc trạng thái phòng hiện tại; lấy snapshot mới.')
        if rooms.streams.get(owner, 0) >= 2: raise HTTPException(429, 'Tối đa hai kết nối sự kiện cho mỗi phiên.')
        rooms.streams[owner] = rooms.streams.get(owner, 0) + 1
        released = False
        def release():
            nonlocal released
            if not released:
                released = True
                rooms.streams[owner] = max(0, rooms.streams.get(owner, 1) - 1)
        async def stream():
            last, seconds = -1, 0
            try:
                while seconds <= 25:
                    if await request.is_disconnected(): break
                    try: user(request)
                    except HTTPException:
                        yield 'event: session_expired\ndata: {}\n\n'; break
                    try:
                        value = await asyncio.to_thread(view, room_id, owner)
                    except HTTPException:
                        yield 'event: access_changed\ndata: {}\n\n'; break
                    if value['event_index'] != last or seconds % 10 == 0:
                        yield 'id: ' + str(value['event_index']) + '\nevent: snapshot\ndata: ' + dump(value) + '\n\n'
                        last = value['event_index']
                    else: yield ': heartbeat\n\n'
                    if once or value['phase'] in TERMINAL: break
                    seconds += 1
                    await asyncio.sleep(1)
            finally:
                release()
        return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'}, background=BackgroundTask(release))

    @app.post('/api/rooms/{room_id}/questions/{question_id}/chat')
    async def help_question(room_id: str, question_id: str, body: RoomHelp, request: Request, background: BackgroundTasks, owner=Depends(user)):
        with database.connection(write=True) as db:
            room = rooms.advance(db, rooms.room(db, room_id)); rooms.member(db, room_id, owner)
            if room['phase'] not in TERMINAL or active_test(db, owner, room['course_id']):
                return JSONResponse(status_code=403, content={'detail': 'Hỏi AI sau khi phòng/lượt kiểm tra đã kết thúc.'})
            if body.question_id != question_id: raise HTTPException(422, 'Chọn đúng câu của phòng.')
            question = next((q for q in json.loads(room['bank_json'])[:room['closed_count']] if q['id'] == question_id), None)
            if not question: raise HTTPException(404, 'Câu chưa được đóng hoặc không thuộc phòng.')
            source = json.loads(room['sources_json']); fragments = [source[ref] for ref in question['source_refs']]
            own = db.execute('SELECT answer_json,correct,points FROM quiz_answers WHERE room_id=? AND user_id=? AND question_index=?', (room_id, owner, json.loads(room['bank_json']).index(question))).fetchone()
            answer = json.loads(own['answer_json']) if own else None
            student = {'raw_answer': answer, 'normalized_answer': normalized_answer(question, answer) if own else None,
                       'correct': bool(own['correct']) if own else None, 'points': own['points'] if own else 0, 'grading': 'fixed'}
            context = {'course_revision': room['course_revision'], 'question': question, 'student': student,
                       'reference_warning': rooms.warning(db, room, question), 'message': body.message}
            history = [{'role': r['role'], **json.loads(r['content_json'])} for r in db.execute('SELECT role,content_json FROM quiz_messages WHERE room_id=? AND user_id=? AND question_id=? ORDER BY created_at DESC,rowid DESC LIMIT 6', (room_id, owner, question_id)).fetchall()][::-1]
        payload = {'room_id': room_id, 'question_id': question_id, 'course_id': room['course_id'], 'course_revision': room['course_revision'], 'message': body.message}
        identity = jobs.identity(request, 'chat', payload, owner=owner)
        def prepare(db):
            db.execute('INSERT INTO quiz_messages VALUES (?,?,?,?,?,?,?)', (uid(), room_id, owner, question_id, 'user', dump({'text': body.message}), rooms.now()))
        async def work(job_id):
            prefs = {'language': question.get('content_language', 'source')}
            reply = await generate_checked(ChatReply, 'Giải thích câu trong phòng đã kết thúc, dùng đúng câu và nguồn đã chốt; kết quả chấm cố định đã có trong student, không tự chấm lại hoặc đổi điểm/nội dung khóa. normalized_answer đã giải ID lựa chọn. Giải thích tại sao lựa chọn của người học đúng/sai. Nếu có reference_warning hoặc đáp án mâu thuẫn nguồn, nói rõ cần xem lại thay vì bảo vệ key cũ. Nếu thiếu nguồn báo rõ. ' + language_instruction(prefs) + dump({**context, 'history': history}), fragments)
            validate_language(reply, prefs)
            with database.connection(write=True) as db:
                jobs.check(db, job_id)
                db.execute('INSERT INTO quiz_messages VALUES (?,?,?,?,?,?,?)', (uid(), room_id, owner, question_id, 'assistant', dump(reply), rooms.now()))
                jobs.finish(db, job_id, reply)
            return reply
        return jobs.create(owner, 'chat', payload, background, work, identity, prepare)

    @app.get('/api/rooms/{room_id}/questions/{question_id}/chat')
    def help_history(room_id: str, question_id: str, owner=Depends(user)):
        with database.connection(write=True) as db:
            room = rooms.advance(db, rooms.room(db, room_id)); rooms.member(db, room_id, owner)
            if room['phase'] not in TERMINAL or active_test(db, owner, room['course_id']): return JSONResponse(status_code=403, content={'detail': 'Hỏi lại sau khi phòng/lượt kiểm tra kết thúc.'})
            rows = db.execute('SELECT * FROM quiz_messages WHERE room_id=? AND user_id=? AND question_id=? ORDER BY created_at DESC,rowid DESC LIMIT 100', (room_id, owner, question_id)).fetchall()
            return [{'id': r['id'], 'role': r['role'], **json.loads(r['content_json'])} for r in reversed(rows)]

    # Specific POST paths (answers/presence/chat) must be registered before this
    # two-segment action path, otherwise FastAPI would send answers to control.
    app.post('/api/rooms/{room_id}/{action}')(control)
