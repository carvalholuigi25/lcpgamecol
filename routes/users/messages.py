"""Direct messages between accounts: the envelope in the page header.

Any signed-in user can write to any other account. The recipient gets a
notification, a live messagesChanged event, and an email when their profile has
an address. Deleting hides a message for one side only; the row is removed once
both sender and recipient have deleted it.
"""

from contextlib import closing
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from backend.auth.auth import Principal, get_current_principal
from backend.database.database import get_connection
from backend.mail import mailer
from backend.realtime.hub import hub
from routes.admin.users import _accounts
from routes.users.notifications import notify, now

MESSAGES_LIMIT_MAX = 100
MESSAGE_SUBJECT_MAX_LENGTH = 120
MESSAGE_BODY_MAX_LENGTH = 4000
INBOX_LINK = "/profile?inbox=messages"
SEND_MESSAGE_TO_YOURSELF_DISABLED = True

router = APIRouter(prefix="/messages", tags=["messages"])


class MessageCreate(BaseModel):
    recipient: str = Field(min_length=1, max_length=64)
    subject: str = Field(min_length=1, max_length=MESSAGE_SUBJECT_MAX_LENGTH)
    body: str = Field(min_length=1, max_length=MESSAGE_BODY_MAX_LENGTH)
    reply_to: int | None = None

    @field_validator("recipient", "subject")
    @classmethod
    def single_line(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("This field cannot be empty.")
        return value

    @field_validator("body")
    @classmethod
    def strip_body(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Write a message before sending it.")
        return value


def _message(row, username: str) -> dict:
    incoming = row["recipient"].lower() == username.lower()
    return {
        "id": row["id"],
        "sender": row["sender"],
        "recipient": row["recipient"],
        "subject": row["subject"],
        "body": row["body"],
        "reply_to": row["reply_to"],
        "created_at": row["created_at"],
        "read": row["read_at"] is not None,
        "incoming": incoming,
    }


def unread_count(connection, username: str) -> int:
    return connection.execute(
        "SELECT COUNT(*) FROM messages WHERE recipient = ? AND read_at IS NULL AND recipient_deleted = 0",
        (username,),
    ).fetchone()[0]


def _publish_change(username: str, message: dict | None = None) -> None:
    with closing(get_connection()) as connection:
        unread = unread_count(connection, username)
    hub.publish("messagesChanged", {"unread": unread, "message": message}, username=username)


def _own_message(connection, message_id: int, username: str):
    row = connection.execute(
        """
        SELECT * FROM messages WHERE id = ? AND (
            (recipient = ? AND recipient_deleted = 0) OR (sender = ? AND sender_deleted = 0)
        )
        """,
        (message_id, username, username),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    return row


def _email_recipient(recipient: str, sender: str, subject: str, body: str) -> None:
    mailer.send_to_user(
        recipient,
        f"New message from {sender}: {subject}",
        f"{sender} sent you a message on lcpgamecol.\n\n"
        f"Subject: {subject}\n\n{body}\n\n"
        f"Read and reply: {mailer.app_link(INBOX_LINK)}\n",
    )


@router.get("")
def list_messages(
    box: Literal["inbox", "sent"] = "inbox",
    limit: int = Query(default=50, ge=1, le=MESSAGES_LIMIT_MAX),
    principal: Principal = Depends(get_current_principal),
) -> dict:
    if box == "inbox":
        where = "recipient = ? AND recipient_deleted = 0"
    else:
        where = "sender = ? AND sender_deleted = 0"
    with closing(get_connection()) as connection:
        rows = connection.execute(
            f"SELECT * FROM messages WHERE {where} ORDER BY id DESC LIMIT ?",  # where is one of two constants  # nosec B608
            (principal.username, limit),
        ).fetchall()
        unread = unread_count(connection, principal.username)
    return {"items": [_message(row, principal.username) for row in rows], "unread": unread}


@router.get("/recipients")
def list_recipients(principal: Principal = Depends(get_current_principal)) -> list[dict]:
    with closing(get_connection()) as connection:
        names = {
            row["username"].lower(): row["display_name"]
            for row in connection.execute("SELECT username, display_name FROM user_profiles")
        }
    return [
        {"username": account["username"], "display_name": names.get(key), "role": account["role"]}
        for key, account in sorted(_accounts().items())
        if key != principal.username.lower()
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
def send_message(
    body: MessageCreate,
    background_tasks: BackgroundTasks,
    principal: Principal = Depends(get_current_principal),
) -> dict:
    account = _accounts().get(body.recipient.lower())
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    recipient = account["username"]
    if recipient.lower() == principal.username.lower() and SEND_MESSAGE_TO_YOURSELF_DISABLED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot send a message to yourself.")

    with closing(get_connection()) as connection:
        if body.reply_to is not None:
            _own_message(connection, body.reply_to, principal.username)
        cursor = connection.execute(
            "INSERT INTO messages (sender, recipient, subject, body, reply_to, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (principal.username, recipient, body.subject, body.body, body.reply_to, now()),
        )
        connection.commit()
        row = connection.execute("SELECT * FROM messages WHERE id = ?", (cursor.lastrowid,)).fetchone()

    notify(recipient, "message", f"New message from {principal.username}", body.subject, INBOX_LINK)
    _publish_change(recipient, _message(row, recipient))
    _publish_change(principal.username)
    background_tasks.add_task(_email_recipient, recipient, principal.username, body.subject, body.body)
    return _message(row, principal.username)


@router.post("/{message_id}/read")
def mark_read(message_id: int, principal: Principal = Depends(get_current_principal)) -> dict:
    with closing(get_connection()) as connection:
        row = _own_message(connection, message_id, principal.username)
        if row["recipient"].lower() == principal.username.lower():
            connection.execute(
                "UPDATE messages SET read_at = COALESCE(read_at, ?) WHERE id = ?", (now(), message_id)
            )
            connection.commit()
        unread = unread_count(connection, principal.username)
    _publish_change(principal.username)
    return {"unread": unread}


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_message(message_id: int, principal: Principal = Depends(get_current_principal)) -> None:
    username = principal.username.lower()
    with closing(get_connection()) as connection:
        row = _own_message(connection, message_id, principal.username)
        # A message sent to yourself is impossible, so exactly one side matches.
        side = "recipient_deleted" if row["recipient"].lower() == username else "sender_deleted"
        connection.execute(f"UPDATE messages SET {side} = 1 WHERE id = ?", (message_id,))  # side is a constant  # nosec B608
        connection.execute("DELETE FROM messages WHERE id = ? AND sender_deleted = 1 AND recipient_deleted = 1", (message_id,))
        connection.commit()
    _publish_change(principal.username)
