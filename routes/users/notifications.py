"""Notifications for the signed-in user: the bell in the page header.

Other features call notify() to add one (a reply to your feedback, a new message,
new feedback for administrators). Each change is pushed to the owner's open pages
as a notificationsChanged event so the unread badge updates live.
"""

from contextlib import closing
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.auth.auth import Principal, get_current_principal
from backend.database.database import get_connection
from backend.realtime.hub import hub

NOTIFICATIONS_LIMIT_MAX = 100
# Older notifications are dropped so the table cannot grow without bound.
NOTIFICATIONS_KEPT_PER_USER = 200

router = APIRouter(prefix="/notifications", tags=["notifications"])


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _notification(row) -> dict:
    return {
        "id": row["id"],
        "kind": row["kind"],
        "title": row["title"],
        "body": row["body"],
        "link": row["link"],
        "created_at": row["created_at"],
        "read": row["read_at"] is not None,
    }


def unread_count(connection, username: str) -> int:
    return connection.execute(
        "SELECT COUNT(*) FROM notifications WHERE username = ? AND read_at IS NULL", (username,)
    ).fetchone()[0]


def _publish_change(username: str, notification: dict | None = None) -> None:
    with closing(get_connection()) as connection:
        unread = unread_count(connection, username)
    hub.publish("notificationsChanged", {"unread": unread, "notification": notification}, username=username)


def notify(username: str, kind: str, title: str, body: str | None = None, link: str | None = None) -> dict:
    """Add a notification for a user, push it to their open pages, and return it."""
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            "INSERT INTO notifications (username, kind, title, body, link, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (username, kind, title, body, link, now()),
        )
        connection.execute(
            """
            DELETE FROM notifications WHERE username = ? AND id NOT IN (
                SELECT id FROM notifications WHERE username = ? ORDER BY id DESC LIMIT ?
            )
            """,
            (username, username, NOTIFICATIONS_KEPT_PER_USER),
        )
        connection.commit()
        row = connection.execute("SELECT * FROM notifications WHERE id = ?", (cursor.lastrowid,)).fetchone()
    notification = _notification(row)
    _publish_change(username, notification)
    return notification


@router.get("")
def list_notifications(
    limit: int = Query(default=30, ge=1, le=NOTIFICATIONS_LIMIT_MAX),
    principal: Principal = Depends(get_current_principal),
) -> dict:
    with closing(get_connection()) as connection:
        rows = connection.execute(
            "SELECT * FROM notifications WHERE username = ? ORDER BY id DESC LIMIT ?",
            (principal.username, limit),
        ).fetchall()
        unread = unread_count(connection, principal.username)
    return {"items": [_notification(row) for row in rows], "unread": unread}


@router.post("/read-all")
def mark_all_read(principal: Principal = Depends(get_current_principal)) -> dict:
    with closing(get_connection()) as connection:
        connection.execute(
            "UPDATE notifications SET read_at = ? WHERE username = ? AND read_at IS NULL",
            (now(), principal.username),
        )
        connection.commit()
    _publish_change(principal.username)
    return {"unread": 0}


@router.post("/{notification_id}/read")
def mark_read(notification_id: int, principal: Principal = Depends(get_current_principal)) -> dict:
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            "UPDATE notifications SET read_at = COALESCE(read_at, ?) WHERE id = ? AND username = ?",
            (now(), notification_id, principal.username),
        )
        connection.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
        unread = unread_count(connection, principal.username)
    _publish_change(principal.username)
    return {"unread": unread}


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notification(notification_id: int, principal: Principal = Depends(get_current_principal)) -> None:
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            "DELETE FROM notifications WHERE id = ? AND username = ?", (notification_id, principal.username)
        )
        connection.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    _publish_change(principal.username)
