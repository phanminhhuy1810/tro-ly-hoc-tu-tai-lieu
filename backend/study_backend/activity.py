"""Private, server-recorded learning activity and bounded proposed rewards.

Only a submitted round or five distinct reviewed cards qualifies a study day.
Heartbeats estimate visible study time; neither a page view nor a heartbeat
proves attention, mastery, or a completed round.
"""
import hashlib
import json
import uuid
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, HTTPException
from pydantic import Field
from .models import Model


def dump(value):
    return json.dumps(value, ensure_ascii=False)


class ActivityProfile(Model):
    timezone: str = Field(min_length=1, max_length=100)


class CheckInRequest(Model):
    pass  # Date and owner always come from the server, never from the client.


class Pulse(Model):
    course_id: str
    unit_id: str
    expected_revision: int = Field(ge=1)
    mode: Literal['learn', 'cards', 'practice']
    lease_id: str | None = None
    expected_sequence: int = Field(default=0, ge=0)


class Activity:
    def __init__(self, database, economy, course_snapshot, course_ids, unit_from, weak_query):
        self.database = database
        self.economy = economy
        self.course = course_snapshot
        self.course_ids = course_ids
        self.unit = unit_from
        self.weak = weak_query

    def zone(self, db, owner):
        row = db.execute('SELECT timezone FROM activity_profiles WHERE owner_id=?', (owner,)).fetchone()
        return ZoneInfo(row[0] if row else self.economy.policy['default_timezone'])

    def event(self, db, owner, key, kind, course_id=None, unit_id=None, data=None):
        changed = db.execute('INSERT OR IGNORE INTO activity_events VALUES (?,?,?,?,?,?,?,?)',
                             (uuid.uuid4().hex, owner, key, kind, course_id, unit_id,
                              dump(data or {}), self.economy.stamp())).rowcount
        return bool(changed)

    def events(self, db, owner):
        return [{**dict(row), 'data': json.loads(row['data_json'])}
                for row in db.execute('SELECT * FROM activity_events WHERE owner_id=? ORDER BY occurred_at,id', (owner,))]

    def reward(self, db, owner, name, key, category, context=None):
        if not self.economy.enabled:
            return {'amount': 0, 'disabled_for_test': True}
        return self.economy.award(db, owner, self.economy.policy['rewards'][name], key, category, context)

    def achievement(self, db, owner, code, context=None):
        added = db.execute('INSERT OR IGNORE INTO achievements VALUES (?,?,?,?)',
                           (owner, code, dump(context or {}), self.economy.stamp())).rowcount
        if added:
            return self.reward(db, owner, code, 'achievement:' + code, 'achievement', context)

    def streak(self, db, owner):
        today = self.economy.now().astimezone(self.zone(db, owner)).date()
        dates = sorted({datetime.fromisoformat(e['occurred_at']).astimezone(self.zone(db, owner)).date()
                        for e in self.events(db, owner) if e['kind'] in {'practice_completed', 'card_round_completed'}})
        longest = run = 0
        previous = None
        for day in dates:
            run = run + 1 if previous and day == previous + timedelta(days=1) else 1
            longest = max(longest, run)
            previous = day
        cursor = today if today in dates else today - timedelta(days=1)
        current = 0
        date_set = set(dates)
        while cursor in date_set:
            current += 1
            cursor -= timedelta(days=1)
        monday = today - timedelta(days=today.weekday())
        return {'current': current, 'longest': longest, 'active_days': len(dates),
                'timezone': str(self.zone(db, owner)), 'today': today.isoformat(),
                'week': [{'date': (monday + timedelta(days=i)).isoformat(),
                          'completed': monday + timedelta(days=i) in date_set} for i in range(7)]}

    def attend(self, db, owner, source):
        """Studying is today's check-in (Vietnam day); opening a page is not. Idempotent per day."""
        zone = ZoneInfo('Asia/Ho_Chi_Minh')
        today = self.economy.now().astimezone(zone).date()
        return self.event(db, owner, 'check-in:' + today.isoformat(), 'daily_check_in',
                          data={'date': today.isoformat(), 'timezone': str(zone), 'source': source})

    def check_in(self, db, owner, submit=False):
        zone = ZoneInfo('Asia/Ho_Chi_Minh')
        today = self.economy.now().astimezone(zone).date()
        added = self.attend(db, owner, 'button') if submit else False
        dates = {datetime.fromisoformat(event['data']['date']).date()
                 for event in self.events(db, owner) if event['kind'] == 'daily_check_in'}
        cursor = today if today in dates else today - timedelta(days=1)
        current = 0
        while cursor in dates:
            current += 1
            cursor -= timedelta(days=1)
        monday = today - timedelta(days=today.weekday())
        return {'today': today.isoformat(), 'timezone': str(zone), 'checked_today': today in dates,
                'newly_checked': added, 'current_streak': current, 'total_days': len(dates),
                'week': [{'date': (monday + timedelta(days=i)).isoformat(),
                          'checked': monday + timedelta(days=i) in dates} for i in range(7)],
                'coin_awarded': 0, 'coin_reward_not_configured': True,
                'counts_as_study': False}

    def milestones(self, db, owner, course_id=None):
        rewards = []
        streak = self.streak(db, owner)
        for minimum, code in [(3, 'study_day_3'), (7, 'study_day_7')]:
            if streak['longest'] >= minimum:
                rewards.append(self.achievement(db, owner, code, {'timezone': streak['timezone']}))
        count = db.execute('SELECT count(*) FROM (SELECT DISTINCT course_id,unit_id FROM unit_completions WHERE owner_id=?)', (owner,)).fetchone()[0]
        if count >= 5:
            rewards.append(self.achievement(db, owner, 'five_units'))
        if course_id and course_id in self.course_ids(db, owner):
            course = self.course(db, course_id, owner)
            # Uncreated outline units still count; completing just the generated
            # first lesson cannot earn a whole-course achievement.
            if course['content']['units'] and all(u['completed'] for u in course['content']['units']):
                code = 'course_complete:' + course_id
                if db.execute('INSERT OR IGNORE INTO achievements VALUES (?,?,?,?)',
                              (owner, code, dump({'course_id': course_id}), self.economy.stamp())).rowcount:
                    rewards.append(self.reward(db, owner, 'course_complete', 'achievement:' + code, 'achievement'))
        return [r for r in rewards if r]

    def complete(self, db, owner, session):
        items = json.loads(session['items_json'])
        scope = json.loads(session['scope_json'])
        data = {'session_id': session['id'], 'revision': session['course_revision'],
                'questions': len(items), 'exercise': scope.get('exercise', 'practice')}
        if not self.event(db, owner, 'session:' + session['id'], 'practice_completed', session['course_id'], scope.get('unit_id'), data):
            return []
        self.attend(db, owner, 'practice')
        day = self.economy.now().date().isoformat()
        # Repeating the same bank today does not remint a round reward, even if
        # a caller uses a fresh session id. Other banks have a separate daily cap.
        bank = hashlib.sha256(dump(sorted(q.get('question_revision_id', q['id']) for q in items)).encode()).hexdigest()
        key = f'practice:{day}:{session["course_id"]}:{bank}'
        paid = db.execute("SELECT count(*) FROM coin_ledger WHERE owner_id=? AND event_key LIKE ?", (owner, f'practice:{day}:%')).fetchone()[0]
        rewards = []
        if paid < self.economy.policy['rewarded_practice_rounds_per_utc_day']:
            rewards.append(self.reward(db, owner, 'practice', key, 'learning', data))
        rewards.append(self.reward(db, owner, 'daily_practice_mission', 'mission:practice:' + day, 'mission', data))
        if scope.get('exercise') == 'weak':
            rewards.append(self.reward(db, owner, 'weak_mission', 'mission:weak:' + day, 'mission', data))
        rewards.append(self.achievement(db, owner, 'first_session', data))
        return [r for r in rewards + self.milestones(db, owner, session['course_id']) if r]

    def card(self, db, owner, card):
        day = self.economy.now().date().isoformat()
        added = self.event(db, owner, f'card:{day}:{card["id"]}', 'card_reviewed', card.get('course_id'), card.get('unit_id'), {'card_id': card['id']})
        if not added:
            return []
        self.attend(db, owner, 'cards')
        count = db.execute("SELECT count(*) FROM activity_events WHERE owner_id=? AND kind='card_reviewed' AND event_key LIKE ?", (owner, f'card:{day}:%')).fetchone()[0]
        if count < self.economy.policy['cards_per_round']:
            return []
        if not self.event(db, owner, 'card-round:' + day, 'card_round_completed', data={'distinct_cards': self.economy.policy['cards_per_round']}):
            return []
        return [self.reward(db, owner, 'card_round', 'card-round:' + day, 'learning'),
                self.reward(db, owner, 'daily_card_mission', 'mission:cards:' + day, 'mission'),
                *self.milestones(db, owner)]

    def pulse(self, db, owner, body):
        course = self.course(db, body.course_id, owner)
        if course['revision'] != body.expected_revision:
            raise HTTPException(409, 'Khóa đã đổi; làm mới ngữ cảnh trước khi ghi thời gian.')
        self.unit(course, body.unit_id, ready=True)
        current = self.economy.now()
        prior = db.execute('SELECT * FROM activity_leases WHERE owner_id=?', (owner,)).fetchone()
        seconds = 0
        if body.lease_id:
            if not prior or prior['lease_id'] != body.lease_id or prior['sequence'] != body.expected_sequence:
                raise HTTPException(409, 'Nhịp hoạt động đã được xử lý hoặc chuyển sang cửa sổ khác.')
            delta = (current - datetime.fromisoformat(prior['last_at'])).total_seconds()
            # Long gaps/closed tabs do not become credited study time. One
            # account has only one lease, so concurrent tabs cannot multiply it.
            if (prior['course_id'], prior['unit_id'], prior['mode']) == (body.course_id, body.unit_id, body.mode) and 0 < delta <= 60:
                seconds = min(30, int(delta))
            sequence = prior['sequence'] + 1
            lease = prior['lease_id']
        else:
            sequence = 0
            lease = uuid.uuid4().hex
        db.execute('INSERT INTO activity_leases VALUES (?,?,?,?,?,?,?) ON CONFLICT(owner_id) DO UPDATE SET lease_id=excluded.lease_id,course_id=excluded.course_id,unit_id=excluded.unit_id,mode=excluded.mode,sequence=excluded.sequence,last_at=excluded.last_at',
                   (owner, lease, body.course_id, body.unit_id, body.mode, sequence, current.isoformat()))
        if seconds:
            self.event(db, owner, f'pulse:{lease}:{sequence}', 'study_time', body.course_id, body.unit_id, {'seconds': seconds, 'mode': body.mode})
            self.attend(db, owner, 'study_time')
        if body.mode == 'learn':
            self.event(db, owner, f'read:{body.course_id}:{body.expected_revision}:{body.unit_id}', 'reading_viewed', body.course_id, body.unit_id, {'revision': body.expected_revision})
        return {'lease_id': lease, 'sequence': sequence, 'credited_seconds': seconds, 'estimate_only': True, 'study_day_qualified': False}

    def dashboard(self, db, owner, year):
        zone = self.zone(db, owner)
        days = {}
        for event in self.events(db, owner):
            date = datetime.fromisoformat(event['occurred_at']).astimezone(zone).date()
            if date.year != year:
                continue
            day = days.setdefault(date.isoformat(), {'date': date.isoformat(), 'rounds': 0, 'card_reviews': 0, 'seconds': 0, 'qualified': False})
            if event['kind'] in {'practice_completed', 'card_round_completed'}:
                day['rounds'] += 1
                day['qualified'] = True
            if event['kind'] == 'card_reviewed':
                day['card_reviews'] += 1
            if event['kind'] == 'study_time':
                day['seconds'] += event['data']['seconds']
        start = datetime(year, 1, 1).date()
        end = datetime(year + 1, 1, 1).date()
        timeline = [days.get((start + timedelta(days=i)).isoformat(), {'date': (start + timedelta(days=i)).isoformat(), 'rounds': 0, 'card_reviews': 0, 'seconds': 0, 'qualified': False}) for i in range((end-start).days)]
        progress = []
        for course_id in self.course_ids(db, owner):
            course = self.course(db, course_id, owner)
            units = course['content']['units']
            completed = sum(u['completed'] for u in units)
            progress.append({'course_id': course_id, 'title': course['content']['title'], 'completed': completed, 'total': len(units),
                             'percent': round(100 * completed / len(units)) if units else 0,
                             'next_unit_id': next((u['id'] for u in units if u['unlocked'] and not u['completed']), None)})
        return {'year': year, 'timezone': str(zone), 'timeline': timeline, 'weekly_streak': self.streak(db, owner),
                'learning_progress': progress, 'time_is_estimate': True, 'data_source': 'server_activity', 'opening_app_counts_as_study': False}

    def missions(self, db, owner):
        day = self.economy.now().date().isoformat()
        events = self.events(db, owner)
        today = [e for e in events if e['occurred_at'].startswith(day)]
        cards = sum(e['kind'] == 'card_reviewed' for e in today)
        has_weak = any(self.weak(db, owner, course_id) for course_id in self.course_ids(db, owner))
        definitions = [('practice', 'Hoàn thành một lượt luyện', sum(e['kind'] == 'practice_completed' for e in today), 1),
                       ('cards', 'Ôn các thẻ khác nhau', cards, self.economy.policy['cards_per_round']),
                       ('weak', 'Hoàn thành lượt ôn phần hay sai', sum(e['kind'] == 'practice_completed' and e['data']['exercise'] == 'weak' for e in today), 1)]
        daily = []
        for code, title, count, target in definitions:
            reward = db.execute('SELECT amount FROM coin_ledger WHERE owner_id=? AND event_key=?', (owner, f'mission:{code}:{day}')).fetchone()
            daily.append({'code': code, 'title': title, 'progress': min(count, target), 'target': target,
                          'completed': count >= target, 'coin_awarded': reward[0] if reward else 0,
                          'requires_history': code == 'weak', 'suggest_initial_practice': code == 'weak' and not has_weak})
        chains = []
        for course_id in self.course_ids(db, owner):
            course = self.course(db, course_id, owner)
            for unit in course['content']['units']:
                unit_events = [e for e in events if e['course_id'] == course_id and e['unit_id'] == unit['id']]
                steps = [{'code': 'read', 'completed': any(e['kind'] == 'reading_viewed' for e in unit_events)},
                         {'code': 'practice', 'completed': unit['completed']},
                         {'code': 'cards', 'completed': any(e['kind'] == 'card_reviewed' for e in unit_events)}]
                chains.append({'course_id': course_id, 'unit_id': unit['id'], 'steps': steps,
                               'next_step': next((x['code'] for x in steps if not x['completed']), 'complete'),
                               'adds_unlock_condition': False})
        return {'utc_day': day, 'reward_day_timezone': 'UTC', 'daily': daily, 'chains': chains,
                'policy_version': self.economy.policy['version'], 'policy_proposed': True, 'missions_gate_lessons': False}


def register_activity(app, activity, user):
    database = activity.database

    @app.get('/api/activity/check-in')
    def check_in_status(owner=Depends(user)):
        with database.connection() as db:
            return activity.check_in(db, owner)

    @app.post('/api/activity/check-in')
    def check_in(body: CheckInRequest, owner=Depends(user)):
        with database.connection(write=True) as db:
            return activity.check_in(db, owner, submit=True)

    @app.get('/api/activity/profile')
    def profile(owner=Depends(user)):
        with database.connection() as db:
            return {'timezone': str(activity.zone(db, owner)), 'reward_day_timezone': 'UTC'}

    @app.put('/api/activity/profile')
    def change_profile(body: ActivityProfile, owner=Depends(user)):
        try:
            ZoneInfo(body.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise HTTPException(422, 'Dùng tên múi giờ IANA hợp lệ, ví dụ Asia/Ho_Chi_Minh.') from exc
        with database.connection(write=True) as db:
            db.execute('INSERT INTO activity_profiles VALUES (?,?,?) ON CONFLICT(owner_id) DO UPDATE SET timezone=excluded.timezone,updated_at=excluded.updated_at', (owner, body.timezone, activity.economy.stamp()))
        return {'timezone': body.timezone, 'reward_day_timezone': 'UTC', 'old_events_preserved': True}

    @app.post('/api/activity/ping')
    def ping(body: Pulse, owner=Depends(user)):
        with database.connection(write=True) as db:
            return activity.pulse(db, owner, body)

    @app.get('/api/dashboard')
    def dashboard(year: int | None = None, owner=Depends(user)):
        with database.connection() as db:
            year = year or activity.economy.now().astimezone(activity.zone(db, owner)).year
            if not 2000 <= year <= 2100:
                raise HTTPException(422, 'Năm cần trong khoảng 2000–2100.')
            return activity.dashboard(db, owner, year)

    @app.get('/api/missions')
    def missions(owner=Depends(user)):
        with database.connection() as db:
            return activity.missions(db, owner)

    @app.get('/api/achievements')
    def achievements(owner=Depends(user)):
        with database.connection() as db:
            earned = [{**dict(r), 'context': json.loads(r['context_json'])} for r in db.execute('SELECT code,context_json,earned_at FROM achievements WHERE owner_id=? ORDER BY earned_at', (owner,))]
            codes = {r['code'] for r in earned}
            return {'earned': earned, 'next': [k for k in ['first_session', 'study_day_3', 'study_day_7', 'five_units'] if k not in codes],
                    'policy_version': activity.economy.policy['version'], 'policy_proposed': True}
