"""Authenticated current snapshots; reconnect never restarts generation."""
import asyncio
import json

from fastapi import Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask


def register_job_events(app, snapshot, user):
    streams = {}

    @app.get('/api/jobs/{job_id}/events')
    async def events(job_id: str, request: Request, once: bool = False, owner=Depends(user)):
        initial = snapshot(job_id, owner)
        version = (initial.get('progress') or {}).get('version', 0)
        try: cursor = int(request.headers.get('Last-Event-ID', '0'))
        except ValueError: raise HTTPException(422, 'Last-Event-ID cần là số nguyên.') from None
        if not 0 <= cursor <= version: raise HTTPException(409, 'Cursor job không thuộc snapshot hiện tại; tải lại trạng thái.')
        if streams.get(owner, 0) >= 2: raise HTTPException(429, 'Tối đa hai luồng job cho mỗi phiên.')
        streams[owner] = streams.get(owner, 0) + 1
        released = False
        def release():
            nonlocal released
            if not released:
                released = True
                streams[owner] = max(0, streams.get(owner, 1) - 1)
        async def stream():
            last, ticks = None, 0
            try:
                while ticks <= 100:
                    if await request.is_disconnected(): break
                    try: user(request)
                    except HTTPException:
                        yield 'event: session_expired\ndata: {}\n\n'; break
                    try: value = await asyncio.to_thread(snapshot, job_id, owner)
                    except HTTPException:
                        yield 'event: access_changed\ndata: {}\n\n'; break
                    version = (value.get('progress') or {}).get('version', 0)
                    identity = (version, value['status'], value['feedback_deferred'])
                    if identity != last or ticks % 20 == 0:
                        yield 'id: ' + str(version) + '\nevent: snapshot\ndata: ' + json.dumps(value, ensure_ascii=False) + '\n\n'
                        last = identity
                    elif ticks % 4 == 0: yield ': heartbeat\n\n'
                    if once or value['status'] in {'succeeded', 'failed', 'cancelled'}: break
                    ticks += 1
                    await asyncio.sleep(0.25)
            finally: release()
        return StreamingResponse(stream(), media_type='text/event-stream',
            headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'}, background=BackgroundTask(release))
