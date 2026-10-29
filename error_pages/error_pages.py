import re
from datetime import UTC, datetime, timedelta
from html import escape
from pathlib import Path

from starlette.responses import HTMLResponse

ERROR_PAGES_DIRECTORY = Path(__file__).parent.parent / "pages" / "errors"
ERROR_PAGE_FILES = {
    400: "400.html",
    401: "401.html",
    403: "403.html",
    404: "404.html",
    429: "429.html",
    500: "500.html",
}


def accepts_html(accept_header: str) -> bool:
    for media_range in accept_header.split(","):
        media_type, *parameters = media_range.strip().split(";")
        if media_type.strip() not in ("text/html", "application/xhtml+xml"):
            continue
        quality = next(
            (
                parameter.partition("=")[2].strip()
                for parameter in parameters
                if parameter.strip().startswith("q=")
            ),
            "1",
        )
        try:
            if float(quality) > 0:
                return True
        except ValueError:
            continue
    return False


def error_page_response(
    status_code: int, headers: dict[str, str] | None = None
) -> HTMLResponse:
    page_name = ERROR_PAGE_FILES[status_code]
    page_content = (ERROR_PAGES_DIRECTORY / page_name).read_text(encoding="utf-8")
    if status_code == 429:
        retry_after = (headers or {}).get("Retry-After", "0")
        if not retry_after.isdigit():
            retry_after = "0"
        page_content = page_content.replace(
            'data-retry-after="0"', f'data-retry-after="{retry_after}"', 1
        )
    return HTMLResponse(
        content=page_content, status_code=status_code, headers=headers
    )


BLOCKED_PAGE_TITLES = {
    "geoblock": "Not available in your region",
    "vpn": "VPN or proxy detected",
    "lockdown": "The library is closed right now",
}


def blocked_page_response(decision, headers: dict[str, str] | None = None) -> HTMLResponse:
    """The page shown when an access rule (backend.access.rules.Decision) refuses a visitor."""
    page_content = (ERROR_PAGES_DIRECTORY / "blocked.html").read_text(encoding="utf-8")
    until = ""
    if decision.retry_after:
        until = (datetime.now(UTC) + timedelta(seconds=decision.retry_after)).isoformat()
    values = {
        "reason": escape(decision.reason),
        "status_code": str(decision.status_code),
        "title": escape(BLOCKED_PAGE_TITLES[decision.reason]),
        # A message written by an administrator is shown as written, not translated.
        "message_attributes": 'translate="no"' if decision.custom_message else "",
        "message": escape(decision.message),
        "until": escape(until),
    }
    page_content = re.sub(r"\{\{(\w+)\}\}", lambda match: values[match[1]], page_content)
    return HTMLResponse(
        content=page_content, status_code=decision.status_code, headers=headers
    )
