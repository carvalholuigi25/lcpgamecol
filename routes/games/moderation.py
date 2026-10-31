"""Reporting reviews and comments, and the administrators' moderation queue.

The rules (blocked words, report threshold) live in backend/moderation/moderation.py.
routes/games/reviews.py uses the helpers here when posts are written or deleted.
Every change pushes reviewsChanged/commentsChanged to the game's open details and
moderationChanged to the moderation page.
"""

from contextlib import closing
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator

from backend.auth import auth
from backend.auth.auth import Principal, get_current_principal, require_admin
from backend.database.database import get_connection
from backend.gamification import xp
from backend.moderation import moderation
from backend.moderation.rich_text import plain_text
from backend.realtime.hub import hub
from routes.admin.users import _accounts
from routes.users.notifications import notify, now

MODERATION_LINK = "/admin/moderation"
NOTE_MAX_LENGTH = 300
QUEUE_LIMIT = 200
Kind = Literal["review", "comment"]
TABLES = {"review": "game_reviews", "comment": "game_comments"}
CHANGE_EVENTS = {"review": "reviewsChanged", "comment": "commentsChanged"}

router = APIRouter(tags=["moderation"])
admin_router = APIRouter(prefix="/admin/moderation", tags=["admin"], dependencies=[Depends(require_admin)])


class ReportCreate(BaseModel):
    reason: Literal[moderation.REPORT_REASONS]  # type: ignore[valid-type]
    details: str | None = Field(default=None, max_length=NOTE_MAX_LENGTH)

    @field_validator("details")
    @classmethod
    def strip_details(cls, value: str | None) -> str | None:
        return (value or "").strip() or None


class ModeratorNote(BaseModel):
    # Sent to the author with the notification.
    note: str | None = Field(default=None, max_length=NOTE_MAX_LENGTH)

    @field_validator("note")
    @classmethod
    def strip_note(cls, value: str | None) -> str | None:
        return (value or "").strip() or None


# --- helpers for reviews.py ---------------------------------------------------------


def admin_usernames() -> list[str]:
    return [account["username"] for account in _accounts().values() if account["role"] == auth.ROLE_ADMIN]


def alert_admins(title: str, body: str | None = None) -> None:
    for admin in admin_usernames():
        notify(admin, "moderation", title, body, MODERATION_LINK)
    hub.publish("moderationChanged", {})


def open_report_counts(connection, kind: str, item_ids: list[int]) -> dict[int, int]:
    if not item_ids:
        return {}
    placeholders = ", ".join("?" for _ in item_ids)
    rows = connection.execute(
        f"""
        SELECT item_id, COUNT(*) AS reports FROM content_reports
        WHERE kind = ? AND status = 'open' AND item_id IN ({placeholders}) GROUP BY item_id
        """,  # only ? placeholders are interpolated  # nosec B608
        (kind, *item_ids),
    ).fetchall()
    return {row["item_id"]: row["reports"] for row in rows}


def reported_by(connection, kind: str, username: str, item_ids: list[int]) -> set[int]:
    if not item_ids:
        return set()
    placeholders = ", ".join("?" for _ in item_ids)
    rows = connection.execute(
        f"SELECT item_id FROM content_reports WHERE kind = ? AND reporter = ? AND item_id IN ({placeholders})",  # nosec B608
        (kind, username, *item_ids),
    ).fetchall()
    return {row["item_id"] for row in rows}


def forget_reports(connection, kind: str, item_id: int) -> None:
    connection.execute("DELETE FROM content_reports WHERE kind = ? AND item_id = ?", (kind, item_id))


def _game_title(connection, game_id: int) -> str:
    row = connection.execute("SELECT title FROM games WHERE id = ?", (game_id,)).fetchone()
    return row["title"] if row else "a game"


def tell_author(row, kind: str, action: str, game_title: str, note: str | None, moderator: str) -> None:
    """Notify the author when an administrator changes their post (never for their own)."""
    if row["username"].lower() == moderator.lower():
        return
    titles = {
        "removed": f"Your {kind} of {game_title} was removed",
        "hidden": f"Your {kind} of {game_title} was hidden",
        "approved": f"Your {kind} of {game_title} is visible",
    }
    notify(row["username"], "moderation", titles[action], note or None, "/library")


# --- reporting -------------------------------------------------------------------------


def _get_post(connection, kind: str, item_id: int, game_id: int | None = None):
    row = connection.execute(
        f"SELECT * FROM {TABLES[kind]} WHERE id = ?", (item_id,)  # table names come from TABLES  # nosec B608
    ).fetchone()
    if row is None or (game_id is not None and row["game_id"] != game_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{kind.capitalize()} not found")
    return row


def _report(kind: str, game_id: int, item_id: int, body: ReportCreate, principal: Principal) -> dict:
    settings = moderation.load_settings()
    hidden_now = False
    with closing(get_connection()) as connection:
        row = _get_post(connection, kind, item_id, game_id)
        if row["username"].lower() == principal.username.lower():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"You can't report your own {kind}.")
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO content_reports (kind, item_id, game_id, reporter, reason, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (kind, item_id, game_id, principal.username, body.reason, body.details, now()),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"You already reported this {kind}.")
        reports = open_report_counts(connection, kind, [item_id]).get(item_id, 0)
        if row["status"] == moderation.STATUS_VISIBLE and reports >= settings.report_threshold:
            connection.execute(
                f"UPDATE {TABLES[kind]} SET status = ? WHERE id = ?",  # nosec B608
                (moderation.STATUS_HIDDEN, item_id),
            )
            hidden_now = True
        game_title = _game_title(connection, game_id)
        connection.commit()
    if hidden_now:
        alert_admins(f"A {kind} of {game_title} was hidden after {reports} reports", plain_text(row["body"] or "")[:140] or None)
        hub.publish(CHANGE_EVENTS[kind], {"game_id": game_id})
    else:
        hub.publish("moderationChanged", {})
    return {"reported": True, "hidden": hidden_now}


@router.post("/games/{game_id}/reviews/{review_id}/report", status_code=status.HTTP_201_CREATED)
def report_review(
    game_id: int, review_id: int, body: ReportCreate, principal: Principal = Depends(get_current_principal)
) -> dict:
    return _report("review", game_id, review_id, body, principal)


@router.post("/games/{game_id}/comments/{comment_id}/report", status_code=status.HTTP_201_CREATED)
def report_comment(
    game_id: int, comment_id: int, body: ReportCreate, principal: Principal = Depends(get_current_principal)
) -> dict:
    return _report("comment", game_id, comment_id, body, principal)


# --- administrators ---------------------------------------------------------------------


@admin_router.get("/settings")
def get_moderation_settings() -> dict:
    return moderation.load_settings().model_dump()


@admin_router.put("/settings")
def update_moderation_settings(
    body: moderation.ModerationSettings, principal: Principal = Depends(require_admin)
) -> dict:
    return moderation.save_settings(body, principal.username).model_dump()


@admin_router.get("/queue")
def get_moderation_queue() -> dict:
    """Posts that wait for review, are hidden, or have open reports, most reported first."""
    items = []
    with closing(get_connection()) as connection:
        for kind, table in TABLES.items():
            rating = "p.rating" if kind == "review" else "NULL"
            rows = connection.execute(
                f"""
                SELECT p.id, p.game_id, p.username, p.body, p.status, p.created_at, {rating} AS rating,
                       g.title AS game_title, u.display_name,
                       (SELECT COUNT(*) FROM content_reports r
                        WHERE r.kind = ? AND r.item_id = p.id AND r.status = 'open') AS open_reports
                FROM {table} p
                JOIN games g ON g.id = p.game_id
                LEFT JOIN user_profiles u ON u.username = p.username
                WHERE p.status != 'visible' OR open_reports > 0
                LIMIT ?
                """,  # table and column come from TABLES and constants  # nosec B608
                (kind, QUEUE_LIMIT),
            ).fetchall()
            for row in rows:
                reports = connection.execute(
                    """
                    SELECT reporter, reason, details, created_at FROM content_reports
                    WHERE kind = ? AND item_id = ? AND status = 'open' ORDER BY id
                    """,
                    (kind, row["id"]),
                ).fetchall()
                items.append({**dict(row), "kind": kind, "reports": [dict(report) for report in reports]})
    items.sort(key=lambda item: (item["status"] == moderation.STATUS_VISIBLE, -item["open_reports"], item["created_at"]))
    counts = {
        "pending": sum(item["status"] == moderation.STATUS_PENDING for item in items),
        "hidden": sum(item["status"] == moderation.STATUS_HIDDEN for item in items),
        "reported": sum(item["open_reports"] > 0 for item in items),
    }
    return {"items": items, "counts": counts}


def _resolve_reports(connection, kind: str, item_id: int, outcome: str, moderator: str) -> None:
    connection.execute(
        """
        UPDATE content_reports SET status = ?, resolved_by = ?, resolved_at = ?
        WHERE kind = ? AND item_id = ? AND status = 'open'
        """,
        (outcome, moderator, now(), kind, item_id),
    )


def _set_status(kind: str, item_id: int, new_status: str, note: str | None, principal: Principal) -> dict:
    with closing(get_connection()) as connection:
        row = _get_post(connection, kind, item_id)
        connection.execute(
            f"UPDATE {TABLES[kind]} SET status = ? WHERE id = ?", (new_status, item_id)  # nosec B608
        )
        _resolve_reports(
            connection, kind, item_id, "dismissed" if new_status == moderation.STATUS_VISIBLE else "upheld",
            principal.username,
        )
        game_title = _game_title(connection, row["game_id"])
        connection.commit()
    if new_status == moderation.STATUS_VISIBLE:
        # Held posts earn their XP once they are approved.
        xp.award(row["username"], kind, row["game_id"] if kind == "review" else item_id)
        if row["status"] != moderation.STATUS_VISIBLE:
            tell_author(row, kind, "approved", game_title, note, principal.username)
    elif row["status"] != new_status:
        tell_author(row, kind, "hidden", game_title, note, principal.username)
    hub.publish(CHANGE_EVENTS[kind], {"game_id": row["game_id"]})
    hub.publish("moderationChanged", {})
    return {"kind": kind, "id": item_id, "status": new_status}


@admin_router.post("/{kind}/{item_id}/approve")
def approve_post(kind: Kind, item_id: int, body: ModeratorNote | None = None,
                 principal: Principal = Depends(require_admin)) -> dict:
    """Show the post to everyone and dismiss its open reports."""
    return _set_status(kind, item_id, moderation.STATUS_VISIBLE, body.note if body else None, principal)


@admin_router.post("/{kind}/{item_id}/hide")
def hide_post(kind: Kind, item_id: int, body: ModeratorNote | None = None,
              principal: Principal = Depends(require_admin)) -> dict:
    """Hide the post from everyone but its author and administrators."""
    return _set_status(kind, item_id, moderation.STATUS_HIDDEN, body.note if body else None, principal)


@admin_router.post("/{kind}/{item_id}/remove", status_code=status.HTTP_204_NO_CONTENT)
def remove_post(kind: Kind, item_id: int, body: ModeratorNote | None = None,
                principal: Principal = Depends(require_admin)) -> Response:
    """Delete the post and its reports, and tell the author why."""
    with closing(get_connection()) as connection:
        row = _get_post(connection, kind, item_id)
        connection.execute(f"DELETE FROM {TABLES[kind]} WHERE id = ?", (item_id,))  # nosec B608
        forget_reports(connection, kind, item_id)
        game_title = _game_title(connection, row["game_id"])
        connection.commit()
    tell_author(row, kind, "removed", game_title, body.note if body else None, principal.username)
    hub.publish(CHANGE_EVENTS[kind], {"game_id": row["game_id"]})
    hub.publish("moderationChanged", {})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
