"""Forgotten passwords: one-time links that let a user choose a new password.

A user asks for a link with their username or email; it is emailed to the address
in their profile. Administrators can also create a link for any registered user,
to pass on themselves when the user has no email address. Only a hash of each
token is stored, links expire after PASSWORD_RESET_TTL_SECONDS, and using one
signs the user out everywhere.

Accounts configured in AUTH_USERS keep the password from the environment, so they
cannot be reset here.
"""

import hashlib
import os
import secrets
import threading
import time
from collections import deque
from contextlib import closing
from datetime import UTC, datetime

from backend.auth import auth, users
from backend.database.database import get_connection
from backend.mail import mailer

PASSWORD_RESET_TTL_SECONDS = int(os.getenv("PASSWORD_RESET_TTL_SECONDS", "3600"))
PASSWORD_RESET_MAX_PER_CLIENT = int(os.getenv("PASSWORD_RESET_MAX_PER_CLIENT", "5"))
PASSWORD_RESET_WINDOW_SECONDS = int(os.getenv("PASSWORD_RESET_WINDOW_SECONDS", "3600"))
RESET_PATH = "/reset-password"

_requests: dict[str, deque[float]] = {}
_requests_lock = threading.Lock()


class ResetError(Exception):
    """The reset was refused; the message is safe to show to the user."""


class TooManyRequests(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__("Too many reset requests from this connection. Try again later.")
        self.retry_after = retry_after


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def reset_link(token: str) -> str:
    return mailer.app_link(f"{RESET_PATH}?token={token}")


def resettable_username(username: str) -> str | None:
    """Return the stored spelling of a registered (not configured) account."""
    if any(configured.lower() == username.lower() for configured in auth.AUTH_USERS):
        return None
    row = users.get_user(username)
    return row["username"] if row else None


def create_token(username: str, created_by: str) -> str:
    """Create a reset token for a registered user, replacing any unused one."""
    token = secrets.token_urlsafe(32)
    with closing(get_connection()) as connection:
        connection.execute("DELETE FROM password_resets WHERE username = ? AND used_at IS NULL", (username,))
        connection.execute(
            """
            INSERT INTO password_resets (token_hash, username, created_by, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                _hash(token), username, created_by,
                datetime.now(UTC).isoformat(timespec="seconds"),
                int(time.time()) + PASSWORD_RESET_TTL_SECONDS,
            ),
        )
        connection.commit()
    return token


def _check_rate_limit(client_id: str | None) -> None:
    if client_id is None or PASSWORD_RESET_MAX_PER_CLIENT <= 0:
        return
    now = time.monotonic()
    with _requests_lock:
        attempts = _requests.setdefault(client_id, deque())
        while attempts and now - attempts[0] >= PASSWORD_RESET_WINDOW_SECONDS:
            attempts.popleft()
        if len(attempts) >= PASSWORD_RESET_MAX_PER_CLIENT:
            raise TooManyRequests(max(1, int(PASSWORD_RESET_WINDOW_SECONDS - (now - attempts[0]))))
        attempts.append(now)


def _matching_accounts(identifier: str) -> list[str]:
    if "@" in identifier:
        with closing(get_connection()) as connection:
            rows = connection.execute(
                """
                SELECT u.username FROM users u JOIN user_profiles p ON p.username = u.username
                WHERE lower(p.email) = lower(?)
                """,
                (identifier,),
            ).fetchall()
        candidates = [row["username"] for row in rows]
    else:
        candidates = [identifier]
    return [name for name in (resettable_username(candidate) for candidate in candidates) if name]


def request_reset(identifier: str, client_id: str | None) -> list[tuple[str, str]]:
    """Return (username, token) for each account to email.

    The caller answers the same way whether or not anything matched, so the
    response never reveals which usernames or addresses exist.
    """
    _check_rate_limit(client_id)
    identifier = identifier.strip()
    pending = []
    for username in _matching_accounts(identifier):
        if mailer.get_email_address(username):
            pending.append((username, create_token(username, created_by=username)))
    return pending


def email_link(username: str, token: str) -> str:
    minutes = PASSWORD_RESET_TTL_SECONDS // 60
    return mailer.send_to_user(
        username,
        "Reset your lcpgamecol password",
        f"Hi {username},\n\nSomeone asked to reset the password of your lcpgamecol account.\n"
        f"Choose a new password here (the link works once, for {minutes} minutes):\n\n{reset_link(token)}\n\n"
        "If this wasn't you, ignore this email; your password stays the same.\n",
        action_label="Choose a new password",
        action_url=reset_link(token),
    )


def _active_row(connection, token: str):
    row = connection.execute("SELECT * FROM password_resets WHERE token_hash = ?", (_hash(token),)).fetchone()
    if row is None or row["used_at"] or row["expires_at"] < time.time():
        return None
    return row


def check_token(token: str) -> str | None:
    """Return the username a still-valid token belongs to."""
    with closing(get_connection()) as connection:
        row = _active_row(connection, token)
    return row["username"] if row else None


def confirm_reset(token: str, password: str) -> str:
    """Set the new password, use up the token, and sign the user out everywhere."""
    with closing(get_connection()) as connection:
        row = _active_row(connection, token)
        if row is None:
            raise ResetError("This reset link has expired or was already used. Ask for a new one.")
        username = row["username"]
        problem = users.password_problem(password, username)
        if problem:
            raise ResetError(problem)
        connection.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?", (users.hash_password(password), username)
        )
        connection.execute(
            "UPDATE password_resets SET used_at = ? WHERE token_hash = ?",
            (datetime.now(UTC).isoformat(timespec="seconds"), row["token_hash"]),
        )
        connection.execute("DELETE FROM password_resets WHERE username = ? AND used_at IS NULL", (username,))
        connection.commit()
    auth.revoke_sessions(username)
    auth.clear_login_lockouts(username)
    return username
