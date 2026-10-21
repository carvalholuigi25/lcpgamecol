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
