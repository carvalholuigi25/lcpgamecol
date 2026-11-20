"""Shared test helpers."""

import re

from backend.auth.rate_limit import RateLimitMiddleware

BUNDLE_TAG = re.compile(r'<script(?: defer)? src="/public/dist/scripts/all\.min\.js" data-modules="([^"]+)"></script>')


def rate_limiter(app) -> RateLimitMiddleware:
    """Return the app's rate limiter, wherever it sits in the middleware stack.

    The stack is built on the first request. FastAPI may wrap it in its own layers
    (0.162 added ExceptionTelemetryMiddleware), so walk inward instead of assuming
    the rate limiter is the outermost middleware.
    """
    layer = app.middleware_stack
    while layer is not None:
        if isinstance(layer, RateLimitMiddleware):
            return layer
        layer = getattr(layer, "app", None)
    raise LookupError("RateLimitMiddleware is not in the middleware stack")


def bundled_modules(html: str) -> list[str]:
    """Return the script modules a page runs from the all.min.js bundle, in order."""
    tags = BUNDLE_TAG.findall(html)
    assert len(tags) == 1, f"expected one all.min.js tag, found {len(tags)}"
    return tags[0].split()
