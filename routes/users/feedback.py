"""Feedback from users, and the administrators' replies to it.

Any signed-in user can send feedback and follow it on the feedback page
(/feedback). Administrators are notified of new feedback, can change its status
and reply. A reply notifies the user and is emailed to them when their profile
has an address; the outcome is stored in email_status.
"""

from contextlib import closing
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from backend.auth import auth
from backend.auth.auth import Principal, get_current_principal, require_admin
from backend.database.database import get_connection
from backend.gamification import xp
from backend.mail import mailer
from backend.realtime.hub import hub
from routes.admin.users import _accounts
from routes.users.notifications import notify, now

FEEDBACK_SUBJECT_MAX_LENGTH = 120
FEEDBACK_MESSAGE_MAX_LENGTH = 4000
FEEDBACK_REPLY_MAX_LENGTH = 4000
FEEDBACK_PAGE_MAX_LENGTH = 300
FEEDBACK_LINK = "/feedback"
ADMIN_FEEDBACK_LINK = "/feedback#manage"

Category = Literal["bug", "idea", "question", "praise", "other"]
Status = Literal["open", "in_progress", "answered", "closed"]
STATUS_LABELS = {"open": "Open", "in_progress": "In progress", "answered": "Answered", "closed": "Closed"}

router = APIRouter(prefix="/feedback", tags=["feedback"])
admin_router = APIRouter(prefix="/admin/feedback", tags=["admin"], dependencies=[Depends(require_admin)])


class FeedbackCreate(BaseModel):
    category: Category = "other"
    subject: str = Field(min_length=1, max_length=FEEDBACK_SUBJECT_MAX_LENGTH)
    message: str = Field(min_length=1, max_length=FEEDBACK_MESSAGE_MAX_LENGTH)
    page_url: str | None = Field(default=None, max_length=FEEDBACK_PAGE_MAX_LENGTH)

    @field_validator("subject")
    @classmethod
    def single_line(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Add a subject.")
        return value

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Write your feedback before sending it.")
        return value

    @field_validator("page_url")
    @classmethod
    def app_path(cls, value: str | None) -> str | None:
        # Only a path inside the app, so it can never point users somewhere else
        value = (value or "").strip()
        if not value:
            return None
        if not value.startswith("/") or value.startswith("//") or "\\" in value:
            raise ValueError("The page must be a path in this app, such as /library.")
        return value


class FeedbackUpdate(BaseModel):
    status: Status | None = None
    reply: str | None = Field(default=None, max_length=FEEDBACK_REPLY_MAX_LENGTH)

    @field_validator("reply")
    @classmethod
    def strip_reply(cls, value: str | None) -> str | None:
        return (value or "").strip() or None


def _feedback(row, include_admin_fields: bool = False) -> dict:
    item = {
        "id": row["id"],
        "username": row["username"],
        "category": row["category"],
        "subject": row["subject"],
        "message": row["message"],
        "page_url": row["page_url"],
        "status": row["status"],
        "reply": row["reply"],
        "replied_by": row["replied_by"],
        "replied_at": row["replied_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if include_admin_fields:
        item["email_status"] = row["email_status"]
    return item


def _get_row(connection, feedback_id: int):
    row = connection.execute("SELECT * FROM feedback WHERE id = ?", (feedback_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found")
    return row


def _admin_usernames() -> list[str]:
    return [account["username"] for account in _accounts().values() if account["role"] == auth.ROLE_ADMIN]


def _email_reply(feedback_id: int, username: str, subject: str, reply: str, replied_by: str) -> None:
    result = mailer.send_to_user(
        username,
        f"Re: {subject}",
        f"Hi {username},\n\n{replied_by} replied to your feedback \"{subject}\":\n\n{reply}\n\n"
        f"See all your feedback: {mailer.app_link(FEEDBACK_LINK)}\n",
        action_label="See your feedback",
        action_url=mailer.app_link(FEEDBACK_LINK),
    )
    with closing(get_connection()) as connection:
        connection.execute("UPDATE feedback SET email_status = ? WHERE id = ?", (result, feedback_id))
        connection.commit()
    hub.publish("feedbackChanged", {"id": feedback_id})


@router.post("", status_code=status.HTTP_201_CREATED)
def send_feedback(body: FeedbackCreate, principal: Principal = Depends(get_current_principal)) -> dict:
    timestamp = now()
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            """
            INSERT INTO feedback (username, category, subject, message, page_url, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (principal.username, body.category, body.subject, body.message, body.page_url, timestamp, timestamp),
        )
        connection.commit()
        row = _get_row(connection, cursor.lastrowid)

    for admin in _admin_usernames():
        if admin.lower() != principal.username.lower():
            notify(admin, "feedback_new", f"New feedback from {principal.username}", body.subject, ADMIN_FEEDBACK_LINK)
    hub.publish("feedbackChanged", {"id": row["id"]})
    xp.award(principal.username, "feedback", row["id"])
    return _feedback(row)


@router.get("/mine")
def list_my_feedback(principal: Principal = Depends(get_current_principal)) -> list[dict]:
    with closing(get_connection()) as connection:
        rows = connection.execute(
            "SELECT * FROM feedback WHERE username = ? ORDER BY id DESC", (principal.username,)
        ).fetchall()
    return [_feedback(row) for row in rows]


@admin_router.get("")
def list_feedback(feedback_status: Status | None = Query(default=None, alias="status")) -> dict:
    with closing(get_connection()) as connection:
        if feedback_status:
            rows = connection.execute(
                "SELECT * FROM feedback WHERE status = ? ORDER BY id DESC", (feedback_status,)
            ).fetchall()
        else:
            rows = connection.execute("SELECT * FROM feedback ORDER BY id DESC").fetchall()
        counts = dict(connection.execute("SELECT status, COUNT(*) FROM feedback GROUP BY status").fetchall())
    return {
        "items": [_feedback(row, include_admin_fields=True) for row in rows],
        "counts": {key: counts.get(key, 0) for key in STATUS_LABELS},
        "email_enabled": bool(mailer.SMTP_HOST or mailer.MAIL_OUTBOX_DIR),
    }


@admin_router.put("/{feedback_id}")
def update_feedback(
    feedback_id: int,
    body: FeedbackUpdate,
    background_tasks: BackgroundTasks,
    principal: Principal = Depends(require_admin),
) -> dict:
    with closing(get_connection()) as connection:
        current = _get_row(connection, feedback_id)
        new_reply = body.reply if body.reply and body.reply != current["reply"] else None
        new_status = body.status or ("answered" if new_reply and current["status"] in ("open", "in_progress") else None)
        if new_reply is None and (new_status is None or new_status == current["status"]):
            return _feedback(current, include_admin_fields=True)

        timestamp = now()
        if new_reply:
            connection.execute(
                """
                UPDATE feedback SET reply = ?, replied_by = ?, replied_at = ?, email_status = NULL,
                    status = COALESCE(?, status), updated_at = ?
                WHERE id = ?
                """,
                (new_reply, principal.username, timestamp, new_status, timestamp, feedback_id),
            )
        else:
            connection.execute(
                "UPDATE feedback SET status = ?, updated_at = ? WHERE id = ?", (new_status, timestamp, feedback_id)
            )
        connection.commit()
        row = _get_row(connection, feedback_id)

    owner = row["username"]
    if owner.lower() == principal.username.lower():
        pass  # No need to tell administrators about their own changes
    elif new_reply:
        notify(owner, "feedback_reply", f"{principal.username} replied to your feedback", row["subject"], FEEDBACK_LINK)
        background_tasks.add_task(_email_reply, feedback_id, owner, row["subject"], new_reply, principal.username)
    else:
        notify(owner, "feedback_status", f"Your feedback is now {STATUS_LABELS[row['status']].lower()}",
               row["subject"], FEEDBACK_LINK)
    hub.publish("feedbackChanged", {"id": feedback_id})
    return _feedback(row, include_admin_fields=True)


@admin_router.delete("/{feedback_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_feedback(feedback_id: int) -> None:
    with closing(get_connection()) as connection:
        _get_row(connection, feedback_id)
        connection.execute("DELETE FROM feedback WHERE id = ?", (feedback_id,))
        connection.commit()
    hub.publish("feedbackChanged", {"id": feedback_id})
