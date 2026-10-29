from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from backend.access import rules
from backend.auth.auth import AUTH_COOKIE_NAME, ROLE_ADMIN, _decode_access_token
from error_pages.error_pages import accepts_html, blocked_page_response

# Static files and the sign-in endpoints stay reachable, so administrators can always
# sign in from /admin and the blocked page can load its styles.
EXEMPT_PREFIXES = ("/public/", "/nmodules/", "/static/")
EXEMPT_PATHS = {
    "/favicon.ico",
    "/admin",
    "/auth/token",
    "/auth/refresh",
    "/auth/logout",
    "/auth/two-factor/verify",
    "/auth/two-factor/resend",
}


def _is_admin(request: Request) -> bool:
    authorization = request.headers.get("authorization", "")
    scheme, _, bearer = authorization.partition(" ")
    token = bearer if scheme.lower() == "bearer" and bearer else request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        return False
    try:
        return _decode_access_token(token).role == ROLE_ADMIN
    except HTTPException:
        return False


class AccessControlMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if (
            rules.ACCESS_CONTROL_DISABLED
            or path in EXEMPT_PATHS
            or path.startswith(EXEMPT_PREFIXES)
        ):
            return await call_next(request)

        settings = await run_in_threadpool(rules.load_settings)
        if not settings.any_enabled or await run_in_threadpool(_is_admin, request):
            return await call_next(request)

        info = await run_in_threadpool(rules.ip_info_for_request, request, settings)
        decision = rules.evaluate(settings, info)
        if decision is None:
            return await call_next(request)

        rules.record_block(decision, info, path)
        headers = {"Retry-After": str(decision.retry_after)} if decision.retry_after else None
        if accepts_html(request.headers.get("accept", "")):
            return blocked_page_response(decision, headers=headers)
        return JSONResponse(
            {"detail": decision.message, "reason": decision.reason},
            status_code=decision.status_code,
            headers=headers,
        )
