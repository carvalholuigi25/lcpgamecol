"""Send emails to users over SMTP.

Email is optional. With SMTP_HOST unset nothing is sent, unless MAIL_OUTBOX_DIR is
set: then every email is written to that folder as an .eml file instead, which is
handy while developing. Users only get emails when their profile has an address.

Every email has a plain-text part and an HTML part built from it with the
templates/email.html layout. Pass action_label and action_url to show a button;
the paragraph of the text that holds the link is left out of the HTML version.

Callers should send from a background task (FastAPI BackgroundTasks) so a slow
or unreachable mail server never delays a response; send_email never raises.
"""

import html
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
from string import Template

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
EMAIL_TEMPLATE = Template((Path(__file__).parent / "templates" / "email.html").read_text(encoding="utf-8"))
URL_PATTERN = re.compile(r"https?://[^\s<>\"]+")
# A paragraph that is only a sign-in code (123456) or a recovery code (abcd-efgh) is shown large.
CODE_PATTERN = re.compile(r"^(\d{4,8}|[a-z0-9]{4}-[a-z0-9]{4})$")

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


def _linkify(escaped: str) -> str:
    return URL_PATTERN.sub(
        lambda match: f'<a class="email-link" href="{match.group(0)}" style="color: #245f48;">{match.group(0)}</a>',
        escaped,
    )


def _paragraph_html(paragraph: str) -> str:
    if CODE_PATTERN.fullmatch(paragraph):
        return (
            '<p class="email-code" style="margin: 0 0 16px; padding: 14px 18px; border-radius: 10px; '
            "background: #e1ece4; color: #202823; font: 600 28px/1.2 'Courier New', monospace; "
            f'letter-spacing: 0.25em; text-align: center;">{html.escape(paragraph)}</p>'
        )
    lines = "<br />".join(_linkify(html.escape(line, quote=False)) for line in paragraph.splitlines())
    return f'<p style="margin: 0 0 16px;">{lines}</p>'


def render_html(subject: str, text: str, action_label: str | None = None, action_url: str | None = None) -> str:
    """Lay out a plain-text email in the HTML template. Every value is escaped."""
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if action_url:
        paragraphs = [part for part in paragraphs if action_url not in part]
    action = fallback = ""
    if action_label and action_url:
        url = html.escape(action_url, quote=True)
        action = (
            '<table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin: 8px 0 0;"><tr>'
            f'<td style="border-radius: 999px; background: #245f48;"><a href="{url}" '
            'style="display: inline-block; padding: 12px 24px; color: #fffefa; '
            "font: 700 15px/1 'Trebuchet MS', Arial, sans-serif; text-decoration: none; border-radius: 999px;\">"
            f"{html.escape(action_label)}</a></td></tr></table>"
        )
        fallback = (
            f'If the button does not work, open this link: <a class="email-link" href="{url}" '
            f'style="color: #245f48; word-break: break-all;">{url}</a><br /><br />'
        )
    return EMAIL_TEMPLATE.substitute(
        title=html.escape(subject),
        preheader=html.escape(paragraphs[0][:140] if paragraphs else subject),
        body="\n".join(_paragraph_html(part) for part in paragraphs),
        action=action,
        fallback=fallback,
        app_url=html.escape(APP_BASE_URL, quote=True),
    )


def build_message(
    to: str, subject: str, text: str, action_label: str | None = None, action_url: str | None = None
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = MAIL_FROM
    message["To"] = to
    # Header injection is blocked by EmailMessage, but keep subjects on one line
    subject = " ".join(subject.split())[:200]
    message["Subject"] = subject
    message["Message-ID"] = make_msgid(domain="lcpgamecol")
    message.set_content(text)
    message.add_alternative(render_html(subject, text, action_label, action_url), subtype="html")
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


def send_email(
    to: str | None, subject: str, text: str, action_label: str | None = None, action_url: str | None = None
) -> str:
    """Send one email (plain text with an HTML version) and return one of the STATUS_* values."""
    if not to:
        return STATUS_NO_ADDRESS
    if not SMTP_HOST and not MAIL_OUTBOX_DIR:
        return STATUS_DISABLED
    try:
        message = build_message(to, subject, text, action_label, action_url)
        if not SMTP_HOST:
            _save_to_outbox(message)
            return STATUS_SAVED
        _send_smtp(message)
        return STATUS_SENT
    except (OSError, smtplib.SMTPException, ValueError) as exc:
        logger.warning("Email to %s could not be sent: %s", to, exc)
        return STATUS_FAILED


def send_to_user(
    username: str, subject: str, text: str, action_label: str | None = None, action_url: str | None = None
) -> str:
    """Email a user at the address in their profile, if they have one."""
    return send_email(get_email_address(username), subject, text, action_label, action_url)
