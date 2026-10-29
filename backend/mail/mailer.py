"""Send emails to users over SMTP.

Email is optional. With SMTP_HOST unset nothing is sent, unless MAIL_OUTBOX_DIR is
set: then every email is written to that folder as an .eml file instead, which is
handy while developing. Users only get emails when their profile has an address.

Callers should send from a background task (FastAPI BackgroundTasks) so a slow
or unreachable mail server never delays a response; send_email never raises.
"""

import logging
import os
import re
import smtplib
import ssl
from contextlib import closing
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path

from backend.database.database import get_connection

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
# "starttls" (port 587), "ssl" (port 465) or "none" (a local relay only)
SMTP_SECURITY = os.getenv("SMTP_SECURITY", "starttls").lower()
SMTP_TIMEOUT_SECONDS = int(os.getenv("SMTP_TIMEOUT_SECONDS", "10"))
MAIL_FROM = os.getenv("MAIL_FROM", "lcpgamecol <no-reply@localhost>")
MAIL_OUTBOX_DIR = os.getenv("MAIL_OUTBOX_DIR", "")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

EMAIL_MAX_LENGTH = 254
EMAIL_PATTERN = re.compile(r"^[^@\s<>\"',;]+@[^@\s<>\"',;]+\.[^@\s<>\"',;]+$")

STATUS_SENT = "sent"
STATUS_SAVED = "saved"
STATUS_DISABLED = "disabled"
STATUS_NO_ADDRESS = "no_address"
STATUS_FAILED = "failed"

logger = logging.getLogger(__name__)


def email_problem(address: str) -> str | None:
    if len(address) > EMAIL_MAX_LENGTH:
        return f"Email addresses must be {EMAIL_MAX_LENGTH} characters or fewer."
    if not EMAIL_PATTERN.fullmatch(address):
        return "Enter a valid email address."
    return None


def app_link(path: str) -> str:
    return f"{APP_BASE_URL}{path}"


def get_email_address(username: str) -> str | None:
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT email FROM user_profiles WHERE username = ?", (username,)
        ).fetchone()
    return row["email"] if row and row["email"] else None


def build_message(to: str, subject: str, text: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = MAIL_FROM
    message["To"] = to
    # Header injection is blocked by EmailMessage, but keep subjects on one line
    message["Subject"] = " ".join(subject.split())[:200]
    message["Message-ID"] = make_msgid(domain="lcpgamecol")
    message.set_content(text)
    return message


def _save_to_outbox(message: EmailMessage) -> None:
    outbox = Path(MAIL_OUTBOX_DIR)
    outbox.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    (outbox / f"{stamp}.eml").write_bytes(message.as_bytes())


def _send_smtp(message: EmailMessage) -> None:
    context = ssl.create_default_context()
    if SMTP_SECURITY == "ssl":
        client = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS, context=context)
    else:
        client = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS)
    with client:
        if SMTP_SECURITY == "starttls":
            client.starttls(context=context)
        if SMTP_USERNAME:
            client.login(SMTP_USERNAME, SMTP_PASSWORD)
        client.send_message(message)


def send_email(to: str | None, subject: str, text: str) -> str:
    """Send one plain-text email and return one of the STATUS_* values."""
    if not to:
        return STATUS_NO_ADDRESS
    if not SMTP_HOST and not MAIL_OUTBOX_DIR:
        return STATUS_DISABLED
    try:
        message = build_message(to, subject, text)
        if not SMTP_HOST:
            _save_to_outbox(message)
            return STATUS_SAVED
        _send_smtp(message)
        return STATUS_SENT
    except (OSError, smtplib.SMTPException, ValueError) as exc:
        logger.warning("Email to %s could not be sent: %s", to, exc)
        return STATUS_FAILED


def send_to_user(username: str, subject: str, text: str) -> str:
    """Email a user at the address in their profile, if they have one."""
    return send_email(get_email_address(username), subject, text)
