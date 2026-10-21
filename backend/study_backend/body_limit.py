"""Bound incoming API bodies before multipart parsing can spool large files."""
from starlette.responses import JSONResponse
from .source_limits import MAX_BYTES


class BodyLimit:
    def __init__(self, app, limit):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] in {"GET", "HEAD", "OPTIONS"} or not scope["path"].startswith("/api/"):
            return await self.app(scope, receive, send)
        messages, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > self.limit:
                return await JSONResponse({"detail": f"Request vượt giới hạn upload {MAX_BYTES // 1024 // 1024} MiB và phần header."}, status_code=413)(scope, receive, send)
            messages.append(message)
            if not message.get("more_body", False):
                break

        async def replay():
            return messages.pop(0) if messages else await receive()
        await self.app(scope, replay, send)
