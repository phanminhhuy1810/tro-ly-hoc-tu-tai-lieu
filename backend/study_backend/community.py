"""Local sharing ACLs; course access never implicitly grants original-file access."""
import hashlib
import json
import secrets
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import Depends, HTTPException
from pydantic import Field
from .models import Model
from .lifecycle import require_active, deleted


def stamp(): return datetime.now(timezone.utc).isoformat()
def dump(value): return json.dumps(value, ensure_ascii=False)


class Publication(Model):
    expected_revision: int = Field(ge=1)
    visibility: Literal['private', 'shared', 'public']
    share_original: bool = False


class ApplyPublication(Model):
    expected_revision: int = Field(ge=1)


class Join(Model):
    code: str = Field(min_length=8, max_length=100)


class Feedback(Model):
    liked: bool = False
    rating: int | None = Field(default=None, ge=1, le=5)


class Report(Model):
    reason: str = Field(min_length=1, max_length=2000)
    unit_id: str | None = None
    question_id: str | None = None


class CommunityStore:
    def __init__(self, database): self.database=database

    def role(self, db, course, actor):
        require_active(db,'course',course['id'])
        if course['owner_id']==actor: return 'creator'
        publication=db.execute('SELECT visibility FROM course_publications WHERE course_id=?', (course['id'],)).fetchone()
        member=db.execute("SELECT 1 FROM course_members WHERE course_id=? AND user_id=? AND status='active'", (course['id'],actor)).fetchone()
        if not publication or publication[0]=='private' or not member:
            raise HTTPException(404,'Khóa chưa được chia sẻ/enroll trong không gian của bạn.')
        return 'learner'

    def ids(self, db, actor):
        return [r[0] for r in db.execute("""SELECT c.id FROM courses c WHERE
            NOT EXISTS(SELECT 1 FROM resource_lifecycle l WHERE l.resource_type='course' AND l.resource_id=c.id AND l.deleted_at IS NOT NULL)
            AND (c.owner_id=? OR EXISTS(SELECT 1 FROM course_members m JOIN course_publications p ON p.course_id=m.course_id
                WHERE m.course_id=c.id AND m.user_id=? AND m.status='active' AND p.visibility!='private'))""",(actor,actor))]

    def can_original(self, db, source_id, actor):
        if deleted(db,'source',source_id):return False
        for row in db.execute("SELECT p.source_ids_json,p.course_id FROM course_publications p JOIN course_members m ON m.course_id=p.course_id WHERE m.user_id=? AND m.status='active' AND p.visibility!='private'", (actor,)):
            if deleted(db,'course',row['course_id']):continue
            if source_id in json.loads(row[0]): return True
        return False

    def overview(self, db, course_id):
        require_active(db,'course',course_id)
        row=db.execute('SELECT c.owner_id,c.active_revision,p.visibility,p.updated_at FROM courses c JOIN course_publications p ON p.course_id=c.id WHERE c.id=?', (course_id,)).fetchone()
        if not row or row['visibility']!='public': raise HTTPException(404,'Khóa chưa đăng công khai.')
        content=json.loads(db.execute('SELECT content_json FROM course_revisions WHERE course_id=? AND revision=?',(course_id,row['active_revision'])).fetchone()[0])
        creator=db.execute('SELECT display_name FROM users WHERE id=?',(row['owner_id'],)).fetchone()[0]
        summary=db.execute('SELECT sum(liked),avg(rating),count(rating) FROM community_feedback WHERE course_id=?',(course_id,)).fetchone()
        return {'id':course_id,'title':content['title'],'creator_name':creator,'revision':row['active_revision'],
                'units':[{'id':u['id'],'title':u['title'],'generated':bool(u.get('data'))} for u in content['units']],
                'likes':summary[0] or 0,'rating':round(summary[1],2) if summary[1] is not None else None,'rating_count':summary[2],
                'updated_at':row['updated_at'],'requires_enrollment':True,'original_file_access_is_separate':True}


def register_community(app, store, database, course_snapshot, owned, user, economy=None):
    def enroll(db, course_id, actor):
        require_active(db,'course',course_id)
        row=db.execute('SELECT owner_id FROM courses WHERE id=?',(course_id,)).fetchone()
        if not row: raise HTTPException(404,'Không có khóa này.')
        if row[0] != actor:
            db.execute("INSERT INTO course_members VALUES (?,?,?,?) ON CONFLICT(course_id,user_id) DO UPDATE SET status='active'", (course_id,actor,'active',stamp()))
        return {'course_id':course_id,'separate_progress':True,'separate_notebook_and_chat':True}

    @app.post('/api/courses/{course_id}/publication-preview')
    def publication_preview(course_id: str, body: Publication, owner=Depends(user)):
        with database.connection(write=True) as db:
            owned(db,'courses',course_id,owner)
            course=course_snapshot(db,course_id,owner)
            if course['revision']!=body.expected_revision: raise HTTPException(409,'Khóa đã đổi; xem lại trước khi chia sẻ.')
            if body.visibility!='private' and not any(u.get('data') for u in course['content']['units']):
                raise HTTPException(409,'Tạo và xem lại ít nhất một phần trước khi chia sẻ.')
            source_ids=[]
            for plan_id in {course['plan_id'],*[u.get('source_plan_id',course['plan_id']) for u in course['content']['units']]}:
                plan=owned(db,'plans',plan_id,owner)
                if plan['source_id'] not in source_ids: source_ids.append(plan['source_id'])
            settings={**body.model_dump(),'source_ids':source_ids if body.share_original and body.visibility!='private' else []}
            summary={'title':course['content']['title'],'visibility':body.visibility,'course_revision':course['revision'],
                'shared_material':['lesson','cards','practice_bank','selected_source_excerpts'],
                'private_material_excluded':['learner_progress','notebook','chat','creator_preferences_and_notes','answer_keys_before_submission'],
                'originals':[json.loads(owned(db,'sources',i,owner)['metadata_json'])['name'] for i in settings['source_ids']],
                'warning':'Học viên giữ lịch sử/ghi chú riêng; chuyển về private chặn truy cập khóa và nguồn mới. Quyền file gốc không tự tăng khi khóa đổi nguồn.'}
            proposal_id=uuid.uuid4().hex
            db.execute('INSERT INTO publication_proposals VALUES (?,?,?,?,?,?,?,?)',(proposal_id,owner,course_id,course['revision'],dump(settings),dump(summary),'preview',stamp()))
            return {'publication_id':proposal_id,'preview':summary,'requires_apply':True}

    @app.post('/api/publications/{publication_id}/apply')
    def apply(publication_id: str, body: ApplyPublication, owner=Depends(user)):
        with database.connection(write=True) as db:
            proposal=owned(db,'publication_proposals',publication_id,owner)
            course=owned(db,'courses',proposal['course_id'],owner)
            if proposal['status']!='preview' or body.expected_revision!=proposal['base_revision'] or course['active_revision']!=body.expected_revision:
                raise HTTPException(409,'Bản chia sẻ đã đổi/áp dụng; xem lại trước khi ghi.')
            settings=json.loads(proposal['settings_json'])
            db.execute('INSERT INTO course_publications VALUES (?,?,?,?,?) ON CONFLICT(course_id) DO UPDATE SET visibility=excluded.visibility,source_ids_json=excluded.source_ids_json,updated_at=excluded.updated_at', (course['id'],settings['visibility'],dump(settings['source_ids']),stamp(),stamp()))
            revoked=0
            if settings['visibility']=='private':
                revoked=db.execute("UPDATE course_members SET status='revoked' WHERE course_id=? AND status='active'",(course['id'],)).rowcount
                db.execute('DELETE FROM course_invites WHERE course_id=?',(course['id'],))
            db.execute("UPDATE publication_proposals SET status='applied' WHERE id=?",(publication_id,))
            return {'course_id':course['id'],'visibility':settings['visibility'],'original_source_ids':settings['source_ids'],'revoked_members':revoked,'coin_for_publishing':0}

    @app.post('/api/courses/{course_id}/invite')
    def invite(course_id: str, owner=Depends(user)):
        with database.connection(write=True) as db:
            owned(db,'courses',course_id,owner)
            row=db.execute('SELECT visibility FROM course_publications WHERE course_id=?',(course_id,)).fetchone()
            if not row or row[0]=='private': raise HTTPException(409,'Duyệt chia sẻ trước khi tạo mã mời.')
            code=secrets.token_urlsafe(18)
            db.execute('INSERT INTO course_invites VALUES (?,?,?)',(hashlib.sha256(code.encode()).hexdigest(),course_id,stamp()))
            return {'course_id':course_id,'code':code,'keep_code_private':True}

    @app.post('/api/community/join')
    def join(body: Join, owner=Depends(user)):
        with database.connection(write=True) as db:
            row=db.execute("SELECT i.course_id FROM course_invites i JOIN course_publications p ON p.course_id=i.course_id WHERE token_hash=? AND p.visibility!='private'",(hashlib.sha256(body.code.encode()).hexdigest(),)).fetchone()
            if not row: raise HTTPException(404,'Mã mời không còn hiệu lực.')
            return enroll(db,row[0],owner)

    @app.post('/api/courses/{course_id}/enroll')
    def public_enroll(course_id: str, owner=Depends(user)):
        with database.connection(write=True) as db:
            store.overview(db,course_id)
            return enroll(db,course_id,owner)

    @app.get('/api/community')
    def listing(q: str='', owner=Depends(user)):
        with database.connection() as db:
            items=[store.overview(db,r[0]) for r in db.execute("SELECT course_id FROM course_publications p WHERE visibility='public' AND NOT EXISTS(SELECT 1 FROM resource_lifecycle l WHERE l.resource_type='course' AND l.resource_id=p.course_id AND l.deleted_at IS NOT NULL) ORDER BY updated_at DESC LIMIT 100")]
            return [x for x in items if q.casefold() in x['title'].casefold()]

    @app.get('/api/community/{course_id}')
    def overview(course_id: str, owner=Depends(user)):
        with database.connection() as db:return store.overview(db,course_id)

    @app.put('/api/community/{course_id}/feedback')
    def feedback(course_id: str, body: Feedback, owner=Depends(user)):
        with database.connection(write=True) as db:
            store.overview(db,course_id)
            course=course_snapshot(db,course_id,owner)
            if course['creator_id']==owner: raise HTTPException(409,'Không tự thả tim/đánh giá để nhận thưởng cho bài của mình.')
            db.execute('INSERT INTO community_feedback VALUES (?,?,?,?,?) ON CONFLICT(course_id,user_id) DO UPDATE SET liked=excluded.liked,rating=excluded.rating,updated_at=excluded.updated_at',(course_id,owner,int(body.liked),body.rating,stamp()))
            event=None
            if body.liked or body.rating is not None and body.rating>=4:
                existing=db.execute('SELECT id FROM community_quality_events WHERE course_id=? AND actor_id=?',(course_id,owner)).fetchone()
                if not existing:
                    event=uuid.uuid4().hex
                    db.execute('INSERT INTO community_quality_events VALUES (?,?,?,?,?,?)',(event,course_id,course['creator_id'],owner,'positive_peer_feedback',stamp()))
            reward = None
            if event and economy and economy.enabled:
                reward = economy.award(db, course['creator_id'], economy.policy['rewards']['community_positive'],
                                       'community:' + event, 'community', {'course_id': course_id, 'actor_id': owner})
            return {'feedback_saved': True, 'new_quality_event_id': event, 'coin_awarded': reward['amount'] if reward else 0,
                    'reward': reward, 'coin_policy_pending': False, 'coin_policy_proposed': True}

    @app.post('/api/community/{course_id}/reports')
    def report(course_id: str, body: Report, owner=Depends(user)):
        with database.connection(write=True) as db:
            course=course_snapshot(db,course_id,owner)
            if body.unit_id and body.unit_id not in {u['id'] for u in course['content']['units']}:
                raise HTTPException(422,'Bài báo lỗi không thuộc khóa.')
            if body.question_id:
                from .learning import question_item
                candidates = [question_item(course_id, u['id'], i, q)['id']
                              for u in course['content']['units'] if (not body.unit_id or u['id'] == body.unit_id) and u['unlocked']
                              for i, q in enumerate((u.get('data') or {}).get('questions', []))]
                if body.question_id not in candidates:
                    raise HTTPException(422, 'Câu báo lỗi không thuộc bài/phạm vi đang được xem.')
            report_id=uuid.uuid4().hex
            db.execute('INSERT INTO community_reports VALUES (?,?,?,?,?,?,?,?)',(report_id,course_id,owner,body.unit_id,body.question_id,body.reason,'open',stamp()))
            return {'report_id':report_id,'bank_changed':False,'status':'open'}

    @app.get('/api/courses/{course_id}/reports')
    def reports(course_id: str, owner=Depends(user)):
        with database.connection() as db:
            owned(db,'courses',course_id,owner)
            return [dict(r) for r in db.execute('SELECT id,unit_id,question_id,reason,status,created_at FROM community_reports WHERE course_id=? ORDER BY created_at DESC',(course_id,))]
