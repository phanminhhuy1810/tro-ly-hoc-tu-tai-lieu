"""Course cover: one of the drawn presets or a small image the creator uploads.

No image model is involved: the local text models cannot draw. The image is
kept in SQLite next to the course (small, re-encoded by the browser before
upload) so a backup of the database keeps it.
"""
import re
from datetime import datetime, timezone

from fastapi import Depends, File, HTTPException, Response, UploadFile
from pydantic import Field

from .models import Model

MAX_IMAGE_BYTES = 1_500_000
IMAGE_TYPES = {'image/png': b'\x89PNG\r\n\x1a\n', 'image/jpeg': b'\xff\xd8\xff', 'image/webp': b'RIFF'}
PRESET = re.compile(r'^[a-z]{2,20}-(sage|butter|coral|sky)$')


class PresetCover(Model):
    preset: str = Field(min_length=4, max_length=40)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def cover_info(row):
    if not row:
        return {'kind': 'auto'}
    return {'kind': row['kind'], 'preset': row['preset'], 'updated_at': row['updated_at']}


def register_covers(app, database, course_snapshot, owned, community_ids, user):
    def creator_course(db, course_id, owner):
        course = course_snapshot(db, course_id, owner)
        if course.get('access_role') == 'learner':
            raise HTTPException(403, 'Chỉ người tạo khóa đổi được ảnh bìa.')
        owned(db, 'courses', course_id, owner)
        return course

    @app.get('/api/covers')
    def covers(owner=Depends(user)):
        with database.connection() as db:
            ids = list(community_ids(db, owner))
            if not ids:
                return {}
            marks = ','.join('?' * len(ids))
            rows = db.execute(f'SELECT course_id,kind,preset,updated_at FROM course_covers WHERE course_id IN ({marks})', ids).fetchall()
            return {row['course_id']: cover_info(row) for row in rows}

    @app.put('/api/courses/{course_id}/cover')
    def choose(course_id: str, body: PresetCover, owner=Depends(user)):
        if not PRESET.match(body.preset):
            raise HTTPException(422, 'Ảnh bìa có sẵn không hợp lệ.')
        with database.connection(write=True) as db:
            creator_course(db, course_id, owner)
            db.execute('INSERT INTO course_covers VALUES (?,?,?,?,?,?,?) ON CONFLICT(course_id) DO UPDATE SET '
                       'kind=excluded.kind,preset=excluded.preset,image=NULL,mime=NULL,updated_at=excluded.updated_at',
                       (course_id, owner, 'preset', body.preset, None, None, stamp()))
            return cover_info(db.execute('SELECT * FROM course_covers WHERE course_id=?', (course_id,)).fetchone())

    @app.post('/api/courses/{course_id}/cover/upload')
    async def upload(course_id: str, file: UploadFile = File(...), owner=Depends(user)):
        data = await file.read(MAX_IMAGE_BYTES + 1)
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(413, 'Ảnh lớn hơn 1,5 MB; chọn ảnh nhỏ hơn.')
        mime = next((kind for kind, magic in IMAGE_TYPES.items() if data.startswith(magic)), None)
        if not mime or (mime == 'image/webp' and data[8:12] != b'WEBP'):
            raise HTTPException(415, 'Chỉ nhận ảnh PNG, JPEG hoặc WebP.')
        with database.connection(write=True) as db:
            creator_course(db, course_id, owner)
            db.execute('INSERT INTO course_covers VALUES (?,?,?,?,?,?,?) ON CONFLICT(course_id) DO UPDATE SET '
                       'kind=excluded.kind,preset=NULL,image=excluded.image,mime=excluded.mime,updated_at=excluded.updated_at',
                       (course_id, owner, 'upload', None, data, mime, stamp()))
            return cover_info(db.execute('SELECT * FROM course_covers WHERE course_id=?', (course_id,)).fetchone())

    @app.delete('/api/courses/{course_id}/cover')
    def reset(course_id: str, owner=Depends(user)):
        with database.connection(write=True) as db:
            creator_course(db, course_id, owner)
            db.execute('DELETE FROM course_covers WHERE course_id=?', (course_id,))
            return {'kind': 'auto'}

    @app.get('/api/courses/{course_id}/cover/image')
    def image(course_id: str, owner=Depends(user)):
        with database.connection() as db:
            course_snapshot(db, course_id, owner)
            row = db.execute("SELECT image,mime FROM course_covers WHERE course_id=? AND kind='upload'", (course_id,)).fetchone()
            if not row:
                raise HTTPException(404, 'Khóa này chưa có ảnh bìa tải lên.')
            return Response(row['image'], media_type=row['mime'], headers={'Cache-Control': 'private, max-age=60', 'X-Content-Type-Options': 'nosniff'})
