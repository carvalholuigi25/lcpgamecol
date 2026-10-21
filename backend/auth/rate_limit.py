import os
import threading
import time
from collections import defaultdict, deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from error_pages.error_pages import accepts_html, error_page_response

RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "60"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.requests: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    async def dispatch(self, request: Request, call_next):
        if request.url.path.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".svg")):
            return await call_next(request)

        if request.url.path.lower().endswith((".css", ".js")):
            return await call_next(request)

        if request.url.path.lower().startswith("/public/"):
            return await call_next(request)

        if request.url.path.lower().startswith("/favicon.ico"):
            return await call_next(request)

        if request.url.path.lower().startswith("/docs"):
            return await call_next(request)

        if RATE_LIMIT_REQUESTS <= 0 or RATE_LIMIT_WINDOW_SECONDS <= 0:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with self.lock:
            timestamps = self.requests[client_ip]
            while timestamps and now - timestamps[0] >= RATE_LIMIT_WINDOW_SECONDS:
                timestamps.popleft()
            if len(timestamps) >= RATE_LIMIT_REQUESTS:
                retry_after = max(1, int(RATE_LIMIT_WINDOW_SECONDS - (now - timestamps[0])))
                headers = {"Retry-After": str(retry_after)}
                if accepts_html(request.headers.get("accept", "")):
                    return error_page_response(429, headers=headers)
                return JSONResponse(
                    {"detail": "Rate limit exceeded"},
                    status_code=429,
                    headers=headers,
                )
            timestamps.append(now)
        return await call_next(request)