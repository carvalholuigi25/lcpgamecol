"""Safe file uploads for administrators.

Files are only accepted when their content matches an allowed type (checked by
signature, not by the client's filename or Content-Type), are size-limited while
streaming, are stored under random names outside the static folders, and are
served back as downloads with a locked-down Content-Security-Policy.
"""

import hashlib
import os
import re
import unicodedata
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi import Path as PathParam
from starlette.responses import FileResponse, JSONResponse

from backend.auth.auth import Principal, require_admin
from backend.database.database import get_connection

ADMIN_PRINCIPAL = Depends(require_admin)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
UPLOAD_DIRECTORY = Path(os.getenv("UPLOAD_DIRECTORY", PROJECT_ROOT / "uploads"))
UPLOAD_MAX_BYTES = int(os.getenv("UPLOAD_MAX_BYTES", str(5 * 1024 * 1024)))
UPLOAD_MAX_FILES = int(os.getenv("UPLOAD_MAX_FILES", "500"))
CHUNK_SIZE = 64 * 1024
MULTIPART_OVERHEAD_BYTES = 64 * 1024
UPLOAD_ID_PATTERN = r"^[0-9a-f]{32}$"

# Raster images and PDF only. SVG and HTML are refused because browsers can run
# scripts inside them.
ALLOWED_TYPES = {
    "image/png": {"extensions": (".png",), "inline": True},
    "image/jpeg": {"extensions": (".jpg", ".jpeg"), "inline": True},
    "image/gif": {"extensions": (".gif",), "inline": True},
    "image/webp": {"extensions": (".webp",), "inline": True},
    "application/pdf": {"extensions": (".pdf",), "inline": False},
}
DOWNLOAD_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; img-src 'self'; sandbox",
    "Cache-Control": "private, no-store",
    "X-Content-Type-Options": "nosniff",
}

def _too_large_detail() -> str:
    return f"Files must be {UPLOAD_MAX_BYTES // (1024 * 1024)} MB or smaller."


class UploadBodyLimitMiddleware:
    """Reject oversized upload bodies before they are parsed and spooled to disk."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"].rstrip("/") != "/admin/uploads"
        ):
            await self.app(scope, receive, send)
            return

        limit = UPLOAD_MAX_BYTES + MULTIPART_OVERHEAD_BYTES
        content_length = dict(scope["headers"]).get(b"content-length")
        if content_length is not None and (
            not content_length.isdigit() or int(content_length) > limit
        ):
            response = JSONResponse({"detail": _too_large_detail()}, status_code=413)
            await response(scope, receive, send)
            return

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=_too_large_detail(),
                    )
            return message

        await self.app(scope, limited_receive, send)


router = APIRouter(prefix="/admin/uploads", tags=["admin"], dependencies=[Depends(require_admin)])


def detect_content_type(header: bytes) -> str | None:
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp"
    if header.startswith(b"%PDF-"):
        return "application/pdf"
    return None


def sanitize_filename(filename: str | None) -> str:
    name = unicodedata.normalize("NFKC", filename or "")
    name = re.split(r"[\\/]", name)[-1]
    name = "".join(
        character for character in name if unicodedata.category(character)[0] != "C"
    )
    name = re.sub(r'[<>:"|?*]', "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if len(name) > 120:
        stem, suffix = os.path.splitext(name)
        name = stem[: 120 - len(suffix)] + suffix
    return name or "upload"


def _upload_path(stored_name: str) -> Path:
    directory = UPLOAD_DIRECTORY.resolve()
    path = (directory / stored_name).resolve()
    if path.parent != directory:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")
    return path


def _upload_record(row) -> dict:
    return {
        "id": row["id"],
        "original_name": row["original_name"],
        "content_type": row["content_type"],
        "size_bytes": row["size_bytes"],
        "sha256": row["sha256"],
        "uploaded_by": row["uploaded_by"],
        "created_at": row["created_at"],
        "previewable": ALLOWED_TYPES[row["content_type"]]["inline"],
    }


def _get_upload_row(upload_id: str):
    with closing(get_connection()) as connection:
        row = connection.execute("SELECT * FROM uploads WHERE id = ?", (upload_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")
    return row


@router.get("")
def list_uploads() -> list[dict]:
    with closing(get_connection()) as connection:
        rows = connection.execute("SELECT * FROM uploads ORDER BY created_at DESC, rowid DESC").fetchall()
    return [_upload_record(row) for row in rows]


@router.get("/limits")
def get_upload_limits() -> dict:
    return {
        "max_bytes": UPLOAD_MAX_BYTES,
        "allowed_types": {
            content_type: list(details["extensions"]) for content_type, details in ALLOWED_TYPES.items()
        },
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_file(file: UploadFile, principal: Principal = ADMIN_PRINCIPAL) -> dict:
    original_name = sanitize_filename(file.filename)
    extension = os.path.splitext(original_name)[1].lower()
    allowed_extensions = {ext for details in ALLOWED_TYPES.values() for ext in details["extensions"]}
    if extension not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PNG, JPEG, GIF, WebP, and PDF files can be uploaded.",
        )

    with closing(get_connection()) as connection:
        count = connection.execute("SELECT COUNT(*) FROM uploads").fetchone()[0]
    if count >= UPLOAD_MAX_FILES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The upload storage is full. Delete files before uploading more.",
        )

    UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)
    upload_id = uuid.uuid4().hex
    temporary_path = _upload_path(f"{upload_id}.part")
    digest = hashlib.sha256()
    size = 0
    header = b""
    try:
        with temporary_path.open("xb") as output:
            while chunk := await file.read(CHUNK_SIZE):
                size += len(chunk)
                if size > UPLOAD_MAX_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=_too_large_detail(),
                    )
                if len(header) < 16:
                    header += chunk[: 16 - len(header)]
                digest.update(chunk)
                output.write(chunk)

        if size == 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The file is empty.")
        content_type = detect_content_type(header)
        if content_type is None or extension not in ALLOWED_TYPES[content_type]["extensions"]:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="The file contents do not match an allowed file type.",
            )

        stored_name = f"{upload_id}{ALLOWED_TYPES[content_type]['extensions'][0]}"
        final_path = _upload_path(stored_name)
        os.replace(temporary_path, final_path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    created_at = datetime.now(UTC).isoformat(timespec="seconds")
    try:
        with closing(get_connection()) as connection:
            connection.execute(
                """
                INSERT INTO uploads (id, original_name, stored_name, content_type,
                                     size_bytes, sha256, uploaded_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (upload_id, original_name, stored_name, content_type, size,
                 digest.hexdigest(), principal.username, created_at),
            )
            connection.commit()
    except BaseException:
        final_path.unlink(missing_ok=True)
        raise
    return _upload_record(_get_upload_row(upload_id))


@router.get("/{upload_id}")
def download_upload(upload_id: str = PathParam(pattern=UPLOAD_ID_PATTERN), inline: bool = False) -> FileResponse:
    row = _get_upload_row(upload_id)
    path = _upload_path(row["stored_name"])
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")
    show_inline = inline and ALLOWED_TYPES[row["content_type"]]["inline"]
    return FileResponse(
        path,
        media_type=row["content_type"],
        filename=row["original_name"],
        content_disposition_type="inline" if show_inline else "attachment",
        headers=DOWNLOAD_HEADERS,
    )


@router.delete("/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_upload(upload_id: str = PathParam(pattern=UPLOAD_ID_PATTERN)) -> None:
    row = _get_upload_row(upload_id)
    with closing(get_connection()) as connection:
        connection.execute("DELETE FROM uploads WHERE id = ?", (upload_id,))
        connection.commit()
    _upload_path(row["stored_name"]).unlink(missing_ok=True)
