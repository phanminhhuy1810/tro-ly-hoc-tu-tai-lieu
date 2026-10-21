"""Recoverable source/course deletion, private history, and explicit ACL revocation."""
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from typing import Literal

from fastapi import Depends, HTTPException, Query
from pydantic import Field

from .models import Model
from . import job_progress


def stamp(): return datetime.now(timezone.utc).isoformat()


def lifecycle_state(db, kind, resource_id):
    row = db.execute('SELECT version,deleted_at FROM resource_lifecycle WHERE resource_type=? AND resource_id=?',
                     (kind, resource_id)).fetchone()
    return dict(row) if row else {'version': 0, 'deleted_at': None}


def deleted(db, kind, resource_id):
    return bool(lifecycle_state(db, kind, resource_id)['deleted_at'])


def require_active(db, kind, resource_id):
    if deleted(db, kind, resource_id):
        raise HTTPException(404, 'Nội dung không có trong thư viện đang dùng. Chủ sở hữu có thể xem thùng rác để khôi phục.')


class LifecycleVersion(Model):
    expected_revision: int = Field(ge=0)
    expected_lifecycle_version: int = Field(ge=0)


class ResourceLifecycle:
    def __init__(self, database, jobs, rooms, storage):
        self.database, self.jobs, self.rooms, self.storage = database, jobs, rooms, storage

    def resource(self, db, kind, resource_id, owner):
        table = {'course': 'courses', 'source': 'sources'}[kind]
        row = db.execute('SELECT * FROM '+table+' WHERE id=? AND owner_id=?', (resource_id, owner)).fetchone()
        if not row: raise HTTPException(404, 'Không có nội dung này trong không gian của bạn.')
        if kind == 'course':
            revision = row['active_revision']
            content = db.execute('SELECT content_json FROM course_revisions WHERE course_id=? AND revision=?', (resource_id, revision)).fetchone()
            title = json.loads(content[0])['title']
        else:
            revision = db.execute('SELECT coalesce(max(revision),0) FROM extraction_revisions WHERE source_id=?', (resource_id,)).fetchone()[0]
            title = json.loads(row['metadata_json'])['name']
        state = lifecycle_state(db, kind, resource_id)
        return {'type': kind, 'id': resource_id, 'title': title, 'revision': revision,
                'lifecycle_version': state['version'], 'deleted_at': state['deleted_at']}

    def course_sources(self, db, course_id):
        # Include old revisions: preserving history must not leave old citations
        # pointing to a silently removed source while the course is active.
        rows = db.execute("""SELECT p.source_id FROM course_revisions r JOIN plans p ON p.id=r.plan_id
            WHERE r.course_id=? UNION
            SELECT p.source_id FROM course_revisions r,json_each(r.content_json,'$.units') u
            JOIN plans p ON p.id=json_extract(u.value,'$.source_plan_id') WHERE r.course_id=?""",
                          (course_id, course_id)).fetchall()
        return [r[0] for r in rows]

    def dependencies(self, db, kind, resource_id, restoring=False):
        if restoring:
            if kind == 'course':
                ids = self.course_sources(db, resource_id)
            else:
                metadata = json.loads(db.execute('SELECT metadata_json FROM sources WHERE id=?', (resource_id,)).fetchone()[0])
                ids = [x['source_id'] for x in metadata.get('components', [])]
            return [{'type':'source','id':sid,'reason':'Khôi phục nguồn này trước.'}
                    for sid in ids if deleted(db,'source',sid)]
        if kind == 'course': return []
        result = []
        for row in db.execute('SELECT id FROM courses'):
            if not deleted(db, 'course', row['id']) and resource_id in self.course_sources(db, row['id']):
                result.append({'type':'course','id':row['id'],'reason':'Khóa còn dùng nguồn, kể cả phiên bản đã học.'})
        rows = db.execute("""SELECT s.id FROM sources s,json_each(s.metadata_json,'$.components') c
            WHERE json_extract(c.value,'$.source_id')=?""", (resource_id,)).fetchall()
        for row in rows:
            if not deleted(db,'source',row['id']):
                result.append({'type':'source_collection','id':row['id'],'reason':'Nguồn còn nằm trong một bộ nguồn đang dùng.'})
        return result

    def job_ids(self, db, kind, resource_id):
        field = {'course':'course_id','source':'source_id'}[kind]
        if kind=='source':
            return [r[0] for r in db.execute("""SELECT j.id FROM jobs j LEFT JOIN plans p ON p.id=json_extract(j.payload_json,'$.plan_id')
                WHERE j.status IN ('queued','running') AND (json_extract(j.payload_json,'$.source_id')=?
                OR (j.task='outline' AND p.source_id=?))""",(resource_id,resource_id))]
        return [r[0] for r in db.execute("SELECT id FROM jobs WHERE status IN ('queued','running') AND json_extract(payload_json,?)=?",('$.'+field, resource_id))]

    def details(self, db, kind, resource_id, owner):
        result = self.resource(db, kind, resource_id, owner)
        restoring = bool(result['deleted_at'])
        blockers = self.dependencies(db, kind, resource_id, restoring)
        sessions = rooms = 0
        if kind == 'course':
            sessions = db.execute("SELECT count(*) FROM study_sessions WHERE course_id=? AND status='open'", (resource_id,)).fetchone()[0]
            rooms = db.execute("SELECT count(*) FROM quiz_rooms WHERE course_id=? AND phase NOT IN ('finished','cancelled')", (resource_id,)).fetchone()[0]
        return {**result, 'blockers':blockers, 'can_delete':not restoring and not blockers,
                'can_restore':restoring and not blockers, 'recovery_policy':'recoverable_trash_no_purge',
                'effects':{'jobs_to_cancel':len(self.job_ids(db,kind,resource_id)),
                           'sessions_to_cancel':sessions,'rooms_to_cancel':rooms,
                           'private_history_retained':True,'personal_notes_and_cards_retained':True,
                           'sharing_revoked':kind=='course','restore_publication':'private' if kind=='course' else None}}

    def cancel_jobs(self, db, ids):
        for jid in ids:
            db.execute("UPDATE jobs SET status='cancelled',error_json=?,updated_at=? WHERE id=? AND status IN ('queued','running')",
                       (json.dumps({'code':'RESOURCE_DELETED','retryable':False,'message':'Nguồn hoặc khóa đã chuyển vào thùng rác; phần đã lưu giữ nguyên.'},ensure_ascii=False),stamp(),jid))
            job_progress.terminal(db,jid,'cancelled')
            self.jobs.failed_plan(db,jid)
            if self.jobs.economy:self.jobs.economy.release(db,jid)

    def check_original(self, db, source_id):
        metadata = json.loads(db.execute('SELECT metadata_json FROM sources WHERE id=?',(source_id,)).fetchone()[0])
        digest = hashlib.sha256()
        try:
            with (self.storage/source_id).open('rb') as stream:
                for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
        except OSError:
            raise HTTPException(409,'File gốc đang thiếu hoặc không đọc được; chưa khôi phục để tránh nguồn hỏng.') from None
        if digest.hexdigest()!=metadata['sha256']:
            raise HTTPException(409,'File gốc không khớp checksum đã lưu; chưa khôi phục hoặc thay nội dung.')

    def transition(self, kind, resource_id, owner, body, restore=False):
        cancelled=[]
        with self.database.connection(write=True) as db:
            current = self.resource(db,kind,resource_id,owner)
            if current['revision'] != body.expected_revision:
                raise HTTPException(409,'Nội dung đã đổi; xem lại ảnh hưởng trước khi xóa/khôi phục.')
            already = bool(current['deleted_at']) != restore
            if already and current['lifecycle_version']==body.expected_lifecycle_version+1:
                return {**current,'replayed':True},[]
            if current['lifecycle_version']!=body.expected_lifecycle_version or already:
                raise HTTPException(409,'Trạng thái thùng rác đã đổi; tải lại trước khi thao tác.')
            blockers=self.dependencies(db,kind,resource_id,restore)
            if blockers:
                raise HTTPException(409,{'code':'RESOURCE_DEPENDENCIES','message':'Xử lý nguồn/khóa phụ thuộc trước; dữ liệu chưa thay đổi.','blockers':blockers})
            if kind=='source' and not restore:
                status=db.execute('SELECT status FROM sources WHERE id=?',(resource_id,)).fetchone()[0]
                if status=='parsing':raise HTTPException(409,'Tài liệu đang được đọc; chờ bản trích hoặc lỗi đọc trước khi xóa.')
            if restore and kind=='source':self.check_original(db,resource_id)
            if not restore:
                cancelled=self.job_ids(db,kind,resource_id);self.cancel_jobs(db,cancelled)
                if kind=='course':
                    for row in db.execute("SELECT * FROM quiz_rooms WHERE course_id=? AND phase NOT IN ('finished','cancelled')",(resource_id,)).fetchall():
                        self.rooms.cancel(db,dict(row),'course_deleted')
                    db.execute("UPDATE study_sessions SET status='cancelled',completed_at=? WHERE course_id=? AND status='open'",(stamp(),resource_id))
                    db.execute("UPDATE course_publications SET visibility='private',updated_at=? WHERE course_id=?",(stamp(),resource_id))
                    db.execute("UPDATE course_members SET status='revoked' WHERE course_id=?",(resource_id,))
                    db.execute('DELETE FROM course_invites WHERE course_id=?',(resource_id,))
                    db.execute("UPDATE revision_proposals SET status='discarded' WHERE course_id=? AND status='preview'",(resource_id,))
                    db.execute("UPDATE publication_proposals SET status='discarded' WHERE course_id=? AND status='preview'",(resource_id,))
                else:
                    db.execute("UPDATE source_proposals SET status='discarded' WHERE source_id=? AND status='preview'",(resource_id,))
            version=current['lifecycle_version']+1;at=stamp();deleted_at=None if restore else at
            db.execute('''INSERT INTO resource_lifecycle VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(resource_type,resource_id) DO UPDATE SET version=excluded.version,deleted_at=excluded.deleted_at,
                content_revision=excluded.content_revision,updated_at=excluded.updated_at''',
                       (kind,resource_id,owner,version,deleted_at,current['revision'],at))
            db.execute('INSERT INTO resource_lifecycle_events VALUES (?,?,?,?,?,?,?)',
                       (kind,resource_id,version,owner,'restore' if restore else 'delete',current['revision'],at))
            return {**current,'lifecycle_version':version,'deleted_at':deleted_at,'replayed':False,
                    'history_retained':True,'publication':'private' if kind=='course' else None},cancelled


def register_lifecycle(app,database,jobs,rooms,storage,user):
    service=ResourceLifecycle(database,jobs,rooms,storage)
    app.state.lifecycle=service
    def register_kind(kind,plural):
        @app.get('/api/'+plural+'/{resource_id}/lifecycle')
        def preview(resource_id:str,owner=Depends(user)):
            with database.connection() as db:return service.details(db,kind,resource_id,owner)

        async def change(resource_id,body,owner,restore):
            result,ids=await asyncio.to_thread(service.transition,kind,resource_id,owner,body,restore)
            for jid in ids:
                handle=jobs.active.get(jid)
                if handle:handle.cancel()
            return result

        @app.delete('/api/'+plural+'/{resource_id}')
        async def remove(resource_id:str,body:LifecycleVersion,owner=Depends(user)):
            return await change(resource_id,body,owner,False)

        @app.post('/api/'+plural+'/{resource_id}/restore')
        async def restore(resource_id:str,body:LifecycleVersion,owner=Depends(user)):
            return await change(resource_id,body,owner,True)
    register_kind('source','sources');register_kind('course','courses')

    @app.get('/api/trash')
    def trash(kind:Literal['source','course']|None=None,limit:int=Query(default=20,ge=1,le=100),
              offset:int=Query(default=0,ge=0),owner=Depends(user)):
        with database.connection() as db:
            where='owner_id=? AND deleted_at IS NOT NULL';args=[owner]
            if kind:where+=' AND resource_type=?';args.append(kind)
            total=db.execute('SELECT count(*) FROM resource_lifecycle WHERE '+where,args).fetchone()[0]
            rows=db.execute('SELECT resource_type,resource_id FROM resource_lifecycle WHERE '+where+' ORDER BY deleted_at DESC,resource_id LIMIT ? OFFSET ?',args+[limit,offset]).fetchall()
            return {'items':[service.details(db,r['resource_type'],r['resource_id'],owner) for r in rows],
                    'total':total,'limit':limit,'offset':offset,'has_more':offset+len(rows)<total}
    return service
