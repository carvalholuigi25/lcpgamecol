"""Shared test helpers."""

from backend.auth.rate_limit import RateLimitMiddleware


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
