"""Two-factor sign-in: authenticator app codes (TOTP) or codes sent by email.

Each user chooses a method in their profile. Setting it up stores a pending method
until the user proves it works with a first code; then 10 one-time recovery codes
are issued for when the phone or mailbox is unavailable.

Signing in with a password returns a short-lived challenge token instead of a
session when 2FA is on (see create_challenge). The session is only issued once
verify_challenge accepts a code. Each challenge allows MAX_ATTEMPTS codes.

While developing, an administrator can switch the second step off for every
account from the dashboard (see skip_for_development). The switch only works when
APP_ENV is "development"; on any other server it is refused and ignored.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import struct
import time
from contextlib import closing
from datetime import UTC, datetime, timedelta
from urllib.parse import quote, urlencode

import jwt
import segno
from jwt.exceptions import InvalidTokenError

from backend.auth import auth
from backend.database.database import get_connection
from backend.mail import mailer

METHOD_TOTP = "totp"
METHOD_EMAIL = "email"
METHODS = (METHOD_TOTP, METHOD_EMAIL)
ISSUER = "lcpgamecol"
TOTP_DIGITS = 6
TOTP_PERIOD_SECONDS = 30
# Accept the codes either side of the current one to allow for clock drift.
TOTP_WINDOW = 1
EMAIL_CODE_TTL_SECONDS = 10 * 60
CHALLENGE_TTL_SECONDS = 10 * 60
MAX_ATTEMPTS = 5
MAX_EMAIL_SENDS = 5
RESEND_INTERVAL_SECONDS = 30
RECOVERY_CODE_COUNT = 10
CHALLENGE_TOKEN_TYPE = "2fa"  # a claim value, not a secret  # nosec B105
DEV_MODE = os.getenv("APP_ENV", "production").strip().lower() in ("development", "dev")
DEV_BYPASS_SETTING = "dev_two_factor_bypass"

logger = logging.getLogger(__name__)


class TwoFactorError(Exception):
    """A code was refused; the message is safe to show to the user."""


# --- codes -------------------------------------------------------------------


def generate_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def totp_code(secret: str, step: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(number % 10**TOTP_DIGITS).zfill(TOTP_DIGITS)


def current_step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // TOTP_PERIOD_SECONDS)


def match_totp(secret: str, code: str, last_step: int | None = None, now: float | None = None) -> int | None:
    """Return the time step the code belongs to, or None. A step already used is refused."""
    step = current_step(now)
    for candidate in range(step - TOTP_WINDOW, step + TOTP_WINDOW + 1):
        if last_step is not None and candidate <= last_step:
            continue
        if hmac.compare_digest(totp_code(secret, candidate), code):
            return candidate
    return None


def otpauth_uri(secret: str, username: str) -> str:
    label = quote(f"{ISSUER}:{username}")
    query = urlencode({"secret": secret, "issuer": ISSUER, "digits": TOTP_DIGITS, "period": TOTP_PERIOD_SECONDS})
    return f"otpauth://totp/{label}?{query}"


def qr_svg_data_uri(text: str) -> str:
    return segno.make(text, error="m").svg_data_uri(scale=5, border=2)


def normalize_code(code: str) -> str:
    return "".join(character for character in code.upper() if character.isalnum())


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _email_code() -> str:
    return str(secrets.randbelow(10**TOTP_DIGITS)).zfill(TOTP_DIGITS)


def _recovery_code() -> str:
    raw = base64.b32encode(secrets.token_bytes(5)).decode("ascii")
    return f"{raw[:4]}-{raw[4:8]}".lower()


def mask_email(address: str | None) -> str | None:
    if not address or "@" not in address:
        return None
    name, domain = address.split("@", 1)
    return f"{name[:1]}{'*' * max(len(name) - 1, 1)}@{domain}"


def email_delivery_enabled() -> bool:
    return bool(mailer.SMTP_HOST or mailer.MAIL_OUTBOX_DIR)


# --- stored settings -------------------------------------------------------------


def _settings(connection, username: str):
    return connection.execute("SELECT * FROM user_two_factor WHERE username = ?", (username,)).fetchone()


def enabled_method(username: str) -> str | None:
    with closing(get_connection()) as connection:
        row = _settings(connection, username)
    return row["method"] if row and row["enabled_at"] else None


def status(username: str) -> dict:
    with closing(get_connection()) as connection:
        row = _settings(connection, username)
        recovery_left = connection.execute(
            "SELECT COUNT(*) FROM two_factor_recovery_codes WHERE username = ? AND used_at IS NULL", (username,)
        ).fetchone()[0]
    address = mailer.get_email_address(username)
    enabled = bool(row and row["enabled_at"])
    return {
        "enabled": enabled,
        "method": row["method"] if enabled else None,
        "enabled_at": row["enabled_at"] if enabled else None,
        "pending_method": row["pending_method"] if row else None,
        "recovery_codes_left": recovery_left if enabled else 0,
        "email": mask_email(address),
        "email_available": bool(address) and email_delivery_enabled(),
    }


def _send_code_email(username: str, code: str, purpose: str) -> str:
    return mailer.send_to_user(
        username,
        f"Your lcpgamecol code: {code}",
        f"Hi {username},\n\nYour code to {purpose} is:\n\n{code}\n\n"
        f"It expires in {EMAIL_CODE_TTL_SECONDS // 60} minutes. If this wasn't you, change your password.\n",
    )


def _store_email_code(connection, challenge_id: str, username: str, code: str) -> None:
    now = int(time.time())
    connection.execute(
        """
        INSERT INTO two_factor_challenges (id, username, method, code_hash, expires_at, sends, sent_at)
        VALUES (?, ?, ?, ?, ?, 1, ?)
        ON CONFLICT (id) DO UPDATE SET code_hash = excluded.code_hash, expires_at = excluded.expires_at,
            sends = two_factor_challenges.sends + 1, sent_at = excluded.sent_at, attempts = 0
        """,
        (challenge_id, username, METHOD_EMAIL, _hash(challenge_id + code), now + EMAIL_CODE_TTL_SECONDS, now),
    )


def _setup_id(username: str) -> str:
    return f"setup:{username.lower()}"


def start_setup(username: str, method: str) -> dict:
    """Begin enabling (or switching to) a method. Nothing changes until confirm_setup."""
    if method not in METHODS:
        raise TwoFactorError("Choose an authenticator app or email.")
    if method == METHOD_EMAIL:
        if not mailer.get_email_address(username):
            raise TwoFactorError("Add an email address to your profile first.")
        if not email_delivery_enabled():
            raise TwoFactorError("Email is not set up on this server, so use an authenticator app.")

    secret = generate_secret() if method == METHOD_TOTP else None
    with closing(get_connection()) as connection:
        connection.execute(
            """
            INSERT INTO user_two_factor (username, pending_method, pending_secret) VALUES (?, ?, ?)
            ON CONFLICT (username) DO UPDATE SET pending_method = excluded.pending_method,
                pending_secret = excluded.pending_secret
            """,
            (username, method, secret),
        )
        code = None
        if method == METHOD_EMAIL:
            code = _email_code()
            _store_email_code(connection, _setup_id(username), username, code)
        connection.commit()

    if method == METHOD_TOTP:
        uri = otpauth_uri(secret, username)
        return {"method": method, "secret": secret, "otpauth_uri": uri, "qr_code": qr_svg_data_uri(uri)}
    result = _send_code_email(username, code, "turn on two-factor sign-in")
    if result not in (mailer.STATUS_SENT, mailer.STATUS_SAVED):
        raise TwoFactorError("The code email could not be sent. Try again later.")
    return {"method": method, "email": mask_email(mailer.get_email_address(username))}


def _new_recovery_codes(connection, username: str) -> list[str]:
    codes = [_recovery_code() for _ in range(RECOVERY_CODE_COUNT)]
    connection.execute("DELETE FROM two_factor_recovery_codes WHERE username = ?", (username,))
    connection.executemany(
        "INSERT INTO two_factor_recovery_codes (username, code_hash) VALUES (?, ?)",
        [(username, _hash(normalize_code(code))) for code in codes],
    )
    return codes


def _check_email_code(connection, challenge_id: str, code: str) -> bool:
    row = connection.execute("SELECT * FROM two_factor_challenges WHERE id = ?", (challenge_id,)).fetchone()
    if row is None or row["code_hash"] is None or row["expires_at"] < time.time():
        raise TwoFactorError("The code has expired. Ask for a new one.")
    if row["attempts"] >= MAX_ATTEMPTS:
        raise TwoFactorError("Too many wrong codes. Ask for a new one.")
    if hmac.compare_digest(row["code_hash"], _hash(challenge_id + code)):
        connection.execute("UPDATE two_factor_challenges SET code_hash = NULL WHERE id = ?", (challenge_id,))
        return True
    connection.execute("UPDATE two_factor_challenges SET attempts = attempts + 1 WHERE id = ?", (challenge_id,))
    return False


def confirm_setup(username: str, code: str) -> list[str]:
    """Turn the pending method on once its first code is right; return new recovery codes."""
    code = normalize_code(code)
    with closing(get_connection()) as connection:
        row = _settings(connection, username)
        if row is None or row["pending_method"] is None:
            raise TwoFactorError("Start the setup again.")
        method = row["pending_method"]
        if method == METHOD_TOTP:
            step = match_totp(row["pending_secret"], code)
            valid = step is not None
        else:
            step = None
            valid = _check_email_code(connection, _setup_id(username), code)
        if not valid:
            connection.commit()
            raise TwoFactorError("That code is not right. Try again.")
        connection.execute(
            """
            UPDATE user_two_factor SET method = ?, secret = ?, enabled_at = ?, pending_method = NULL,
                pending_secret = NULL, last_totp_step = ?
            WHERE username = ?
            """,
            (method, row["pending_secret"], datetime.now(UTC).isoformat(timespec="seconds"), step, username),
        )
        connection.execute("DELETE FROM two_factor_challenges WHERE id = ?", (_setup_id(username),))
        codes = _new_recovery_codes(connection, username)
        connection.commit()
    return codes


def regenerate_recovery_codes(username: str) -> list[str]:
    with closing(get_connection()) as connection:
        if not (row := _settings(connection, username)) or not row["enabled_at"]:
            raise TwoFactorError("Two-factor sign-in is off.")
        codes = _new_recovery_codes(connection, username)
        connection.commit()
    return codes


def _stored_dev_bypass(connection):
    return connection.execute(
        "SELECT value, updated_by, updated_at FROM access_settings WHERE name = ?", (DEV_BYPASS_SETTING,)
    ).fetchone()


def dev_bypass_status() -> dict:
    with closing(get_connection()) as connection:
        row = _stored_dev_bypass(connection)
    try:
        enabled = bool(row and json.loads(row["value"]).get("enabled"))
    except (ValueError, AttributeError):
        enabled = False
    return {
        "dev_mode": DEV_MODE,
        "enabled": enabled,
        # Saved but ignored when the server is not in development mode.
        "active": DEV_MODE and enabled,
        "updated_by": row["updated_by"] if row else None,
        "updated_at": row["updated_at"] if row else None,
    }


def skip_for_development(username: str) -> bool:
    """True when the development bypass lets this sign-in go without a code."""
    if not DEV_MODE or not dev_bypass_status()["active"]:
        return False
    logger.warning("Skipped two-factor sign-in for %s: the development bypass is on.", username)
    return True


def set_dev_bypass(enabled: bool, updated_by: str) -> dict:
    if enabled and not DEV_MODE:
        raise TwoFactorError("Two-factor sign-in can only be skipped when the server runs with APP_ENV=development.")
    with closing(get_connection()) as connection:
        connection.execute(
            """
            INSERT INTO access_settings (name, value, updated_by, updated_at) VALUES (?, ?, ?, ?)
            ON CONFLICT (name) DO UPDATE SET value = excluded.value, updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (DEV_BYPASS_SETTING, json.dumps({"enabled": enabled}), updated_by,
             datetime.now(UTC).isoformat(timespec="seconds")),
        )
        connection.commit()
    logger.warning("%s turned the development two-factor bypass %s.", updated_by, "on" if enabled else "off")
    return dev_bypass_status()


def disable(username: str) -> None:
    with closing(get_connection()) as connection:
        connection.execute("DELETE FROM user_two_factor WHERE username = ?", (username,))
        connection.execute("DELETE FROM two_factor_recovery_codes WHERE username = ?", (username,))
        connection.execute("DELETE FROM two_factor_challenges WHERE username = ?", (username,))
        connection.commit()


# --- sign-in challenges -----------------------------------------------------------


def create_challenge(principal: auth.Principal, method: str) -> tuple[dict, str | None]:
    """Return the challenge response for /auth/token and, for email, the code to send."""
    challenge_id = secrets.token_urlsafe(16)
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": principal.username,
            "role": principal.role,
            "type": CHALLENGE_TOKEN_TYPE,
            "jti": challenge_id,
            "iat": now,
            "exp": now + timedelta(seconds=CHALLENGE_TTL_SECONDS),
        },
        auth.JWT_SECRET,
        algorithm=auth.JWT_ALGORITHM,
    )
    code = None
    with closing(get_connection()) as connection:
        if method == METHOD_EMAIL:
            code = _email_code()
            _store_email_code(connection, challenge_id, principal.username, code)
        else:
            connection.execute(
                "INSERT INTO two_factor_challenges (id, username, method, expires_at) VALUES (?, ?, ?, ?)",
                (challenge_id, principal.username, method, int(time.time()) + CHALLENGE_TTL_SECONDS),
            )
        # Forget challenges that can no longer be used.
        connection.execute("DELETE FROM two_factor_challenges WHERE expires_at < ? AND id NOT LIKE 'setup:%'",
                           (int(time.time()) - CHALLENGE_TTL_SECONDS,))
        connection.commit()
    response = {
        "two_factor_required": True,
        "challenge_token": token,
        "method": method,
        "expires_in": CHALLENGE_TTL_SECONDS,
    }
    if method == METHOD_EMAIL:
        response["email"] = mask_email(mailer.get_email_address(principal.username))
    return response, code


def send_challenge_code(username: str, code: str) -> None:
    _send_code_email(username, code, "sign in")


def _decode_challenge(token: str) -> tuple[auth.Principal, str]:
    try:
        claims = jwt.decode(
            token, auth.JWT_SECRET, algorithms=[auth.JWT_ALGORITHM], options={"require": ["sub", "exp", "jti", "type"]}
        )
    except InvalidTokenError:
        raise TwoFactorError("This sign-in has expired. Sign in again.") from None
    if claims["type"] != CHALLENGE_TOKEN_TYPE or claims.get("role") not in auth.VALID_ROLES:
        raise TwoFactorError("This sign-in has expired. Sign in again.")
    return auth.Principal(username=claims["sub"], role=claims["role"]), claims["jti"]


def resend_challenge_code(token: str) -> tuple[str, str]:
    """Make a new code for an email challenge; return (username, code) to send."""
    principal, challenge_id = _decode_challenge(token)
    with closing(get_connection()) as connection:
        row = connection.execute("SELECT * FROM two_factor_challenges WHERE id = ?", (challenge_id,)).fetchone()
        if row is None or row["completed_at"] or row["method"] != METHOD_EMAIL:
            raise TwoFactorError("This sign-in has expired. Sign in again.")
        if row["sends"] >= MAX_EMAIL_SENDS:
            raise TwoFactorError("Too many codes sent. Sign in again.")
        if row["sent_at"] and time.time() - row["sent_at"] < RESEND_INTERVAL_SECONDS:
            raise TwoFactorError("Wait a moment before asking for another code.")
        code = _email_code()
        _store_email_code(connection, challenge_id, principal.username, code)
        connection.commit()
    return principal.username, code


def _use_recovery_code(connection, username: str, code: str) -> bool:
    cursor = connection.execute(
        "UPDATE two_factor_recovery_codes SET used_at = ? WHERE username = ? AND code_hash = ? AND used_at IS NULL",
        (datetime.now(UTC).isoformat(timespec="seconds"), username, _hash(code)),
    )
    return cursor.rowcount == 1


def verify_challenge(token: str, code: str) -> auth.Principal:
    """Accept an authenticator code, an email code, or a recovery code for a challenge."""
    principal, challenge_id = _decode_challenge(token)
    code = normalize_code(code)
    with closing(get_connection()) as connection:
        challenge = connection.execute("SELECT * FROM two_factor_challenges WHERE id = ?", (challenge_id,)).fetchone()
        if challenge is None or challenge["completed_at"]:
            raise TwoFactorError("This sign-in has expired. Sign in again.")
        if challenge["attempts"] >= MAX_ATTEMPTS:
            raise TwoFactorError("Too many wrong codes. Sign in again.")
        settings = _settings(connection, principal.username)
        if settings is None or not settings["enabled_at"]:
            raise TwoFactorError("This sign-in has expired. Sign in again.")

        valid = False
        if len(code) == TOTP_DIGITS and code.isdigit():
            if settings["method"] == METHOD_TOTP:
                step = match_totp(settings["secret"], code, settings["last_totp_step"])
                if step is not None:
                    connection.execute("UPDATE user_two_factor SET last_totp_step = ? WHERE username = ?",
                                       (step, principal.username))
                    valid = True
            elif challenge["code_hash"] and challenge["expires_at"] >= time.time():
                valid = hmac.compare_digest(challenge["code_hash"], _hash(challenge_id + code))
        else:
            valid = _use_recovery_code(connection, principal.username, code)

        if valid:
            connection.execute("UPDATE two_factor_challenges SET completed_at = ?, code_hash = NULL WHERE id = ?",
                               (int(time.time()), challenge_id))
        else:
            connection.execute("UPDATE two_factor_challenges SET attempts = attempts + 1 WHERE id = ?", (challenge_id,))
        connection.commit()
    if not valid:
        raise TwoFactorError("That code is not right. Try again.")
    # The role may have changed since the password step.
    return auth.Principal(username=principal.username, role=auth.get_role_for_username(principal.username))
