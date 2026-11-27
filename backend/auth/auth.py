import logging
import os
import secrets
import sqlite3
import threading
import time
from collections import deque
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jwt.exceptions import InvalidTokenError

from backend.auth import users
from backend.database import database

TOKEN_EXPIRE_SECONDS = int(os.getenv("TOKEN_EXPIRE_SECONDS", "1800"))
REFRESH_TOKEN_EXPIRE_SECONDS = int(
    os.getenv("REFRESH_TOKEN_EXPIRE_SECONDS", "604800")
)
AUTH_COOKIE_NAME = os.getenv("AUTH_COOKIE_NAME", "access_token")
REFRESH_COOKIE_NAME = os.getenv("REFRESH_COOKIE_NAME", "refresh_token")
# Sent only to /auth/... so /auth/refresh and /auth/logout can read it; pages never see it.
REFRESH_COOKIE_PATH = "/auth"
AUTH_COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "false").lower() == "true"
# Without a configured secret, sign with a random per-process key rather than a
# well-known one; tokens then stop working whenever the app restarts.
JWT_SECRET = os.getenv("JWT_SECRET") or secrets.token_urlsafe(32)
JWT_ALGORITHM = "HS256"
AUTH_USERNAME = os.getenv("AUTH_USERNAME", "admin")
# No default password: without AUTH_USERS or AUTH_PASSWORD there is no configured admin.
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "")
LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", "3"))
LOGIN_LOCKOUT_SECONDS = int(os.getenv("LOGIN_LOCKOUT_SECONDS", "60"))
LOGIN_ATTEMPT_WINDOW_SECONDS = int(os.getenv("LOGIN_ATTEMPT_WINDOW_SECONDS", "300"))
REGISTRATION_ENABLED = os.getenv("AUTH_REGISTRATION_ENABLED", "true").lower() == "true"
REGISTRATION_MAX_PER_CLIENT = int(os.getenv("REGISTRATION_MAX_PER_CLIENT", "5"))
REGISTRATION_WINDOW_SECONDS = int(os.getenv("REGISTRATION_WINDOW_SECONDS", "3600"))
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

logger = logging.getLogger(__name__)
if not os.getenv("JWT_SECRET"):
    logger.warning(
        "JWT_SECRET is not set; using a random secret, so sessions end when the app restarts."
    )
elif len(JWT_SECRET) < 32:
    logger.warning("JWT_SECRET is shorter than 32 characters; set a long random value.")

ROLE_ADMIN = "admin"
ROLE_VIEWER = "viewer"
VALID_ROLES = {ROLE_ADMIN, ROLE_VIEWER}


def _load_users() -> dict[str, tuple[str, str]]:
    """Return {username: (password, role)}.

    Configured via AUTH_USERS="user:password:role,user2:password2:role2".
    Falls back to a single admin user from AUTH_USERNAME/AUTH_PASSWORD, and to no
    configured accounts at all when neither sets a password.
    A password may also be a hash from `python -m backend.auth.users hash`.
    """
    raw = os.getenv("AUTH_USERS")
    if not raw:
        if not AUTH_PASSWORD:
            logger.warning(
                "No AUTH_USERS or AUTH_PASSWORD is set, so there is no administrator account; "
                "set one in config.env."
            )
            return {}
        return {AUTH_USERNAME: (AUTH_PASSWORD, ROLE_ADMIN)}

    users: dict[str, tuple[str, str]] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        username, password, role = entry.split(":")
        if role not in VALID_ROLES:
            raise ValueError(f"Invalid role {role!r} for user {username!r}")
        if not password:
            raise ValueError(f"User {username!r} in AUTH_USERS has no password")
        users[username] = (password, role)
    return users


AUTH_USERS = _load_users()
_login_attempts: dict[tuple[str, str], tuple[int, float | None, float]] = {}
_login_attempts_lock = threading.Lock()
_registrations: dict[str, deque[float]] = {}
_registrations_lock = threading.Lock()
_dummy_password_hash: str | None = None
_monotonic = time.monotonic

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)
refresh_token_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)
_oauth2_dependency = Depends(oauth2_scheme)
_refresh_token_dependency = Depends(refresh_token_scheme)


@dataclass(frozen=True)
class Principal:
    username: str
    role: str


def _create_token(
    username: str,
    token_type: str,
    expires_in: int,
    role: str | None = None,
    extra: dict | None = None,
) -> str:
    claims = {
        "iat": time.time(),
        "jti": secrets.token_urlsafe(12),
        "sub": username,
        "type": token_type,
        "exp": datetime.now(UTC) + timedelta(seconds=expires_in),
    }
    if role is not None:
        claims["role"] = role
    if extra:
        claims.update(extra)
    return jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_access_token(username: str, role: str) -> str:
    return _create_token(username, "access", TOKEN_EXPIRE_SECONDS, role=role)


def _new_refresh_token(connection: sqlite3.Connection, username: str, family_id: str) -> str:
    token = _create_token(
        username, "refresh", REFRESH_TOKEN_EXPIRE_SECONDS, extra={"fam": family_id}
    )
    claims = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    connection.execute(
        "INSERT INTO refresh_tokens (jti, username, family_id, expires_at) VALUES (?, ?, ?, ?)",
        (claims["jti"], username, family_id, int(claims["exp"])),
    )
    return token


def create_refresh_token(username: str, family_id: str | None = None) -> str:
    """Issue a refresh token and record its ID, so it can be rotated and revoked.

    All tokens of one sign-in share a family ID; reusing a rotated token revokes the family.
    """
    with closing(database.get_connection()) as connection:
        token = _new_refresh_token(
            connection, username, family_id or secrets.token_urlsafe(12)
        )
        connection.commit()
    return token


def _set_auth_cookies(response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=access_token,
        max_age=TOKEN_EXPIRE_SECONDS,
        httponly=True,
        secure=AUTH_COOKIE_SECURE,
        samesite="lax",
    )
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=REFRESH_TOKEN_EXPIRE_SECONDS,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=AUTH_COOKIE_SECURE,
        samesite="strict",
    )


def clear_auth_cookies(response) -> None:
    response.delete_cookie(
        key=AUTH_COOKIE_NAME, secure=AUTH_COOKIE_SECURE, httponly=True, samesite="lax"
    )
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        secure=AUTH_COOKIE_SECURE,
        httponly=True,
        samesite="strict",
    )


def issue_session(response, principal: Principal) -> dict[str, str]:
    """Set the auth cookies on a response and return the token pair for API clients."""
    token = create_access_token(principal.username, principal.role)
    refresh_token = create_refresh_token(principal.username)
    _set_auth_cookies(response, token, refresh_token)
    return {
        "access_token": token,
        "refresh_token": refresh_token,
        "token_type": "bearer",  # a token type, not a secret  # nosec B105
    }


def sessions_valid_after(username: str) -> float:
    """Timestamp before which this user's tokens are no longer accepted."""
    if not os.path.exists(database.DATABASE_PATH):
        return 0.0
    try:
        with closing(database.get_connection()) as connection:
            row = connection.execute(
                "SELECT sessions_valid_after FROM user_security WHERE username = ?", (username,)
            ).fetchone()
    except sqlite3.OperationalError:
        return 0.0
    return float(row[0]) if row else 0.0


def revoke_sessions(username: str) -> None:
    """Sign a user out everywhere: tokens issued before now stop working."""
    with closing(database.get_connection()) as connection:
        connection.execute(
            """
            INSERT INTO user_security (username, sessions_valid_after) VALUES (?, ?)
            ON CONFLICT (username) DO UPDATE SET sessions_valid_after = excluded.sessions_valid_after
            """,
            (username, time.time()),
        )
        connection.execute(
            "UPDATE refresh_tokens SET revoked_at = ? WHERE username = ? AND revoked_at IS NULL",
            (int(time.time()), username),
        )
        connection.commit()


def _issued_before_revocation(claims: dict) -> bool:
    issued_at = claims.get("iat")
    return isinstance(issued_at, (int, float)) and issued_at < sessions_valid_after(claims["sub"])


def check_password(username: str, password: str) -> bool:
    """Confirm the password of a signed-in user (for sensitive account changes)."""
    credentials = _find_credentials(username)
    if credentials is None:
        _verify_unknown_user(password)
        return False
    return _password_matches(password, credentials[1])


def clear_login_lockouts(username: str) -> None:
    with _login_attempts_lock:
        for key in [key for key in _login_attempts if key[0] == username.lower()]:
            _login_attempts.pop(key, None)


def _find_credentials(username: str) -> tuple[str, str, str] | None:
    """Return (username, password or hash, role) for a configured or registered user."""
    configured = AUTH_USERS.get(username)
    if configured is not None:
        return username, configured[0], configured[1]
    registered = users.get_user(username)
    if registered is not None and registered["role"] in VALID_ROLES:
        return registered["username"], registered["password_hash"], registered["role"]
    return None


def _password_matches(password: str, secret: str) -> bool:
    if users.is_password_hash(secret):
        return users.verify_password(password, secret)
    return secrets.compare_digest(password.encode("utf-8"), secret.encode("utf-8"))


def _verify_unknown_user(password: str) -> None:
    # Spend the same hashing time as a real account so response timing does not
    # reveal which usernames exist.
    global _dummy_password_hash
    if _dummy_password_hash is None:
        _dummy_password_hash = users.hash_password(secrets.token_urlsafe(16))
    users.verify_password(password, _dummy_password_hash)


def _lockout_exception(retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Login locked after {LOGIN_MAX_ATTEMPTS} failed attempts. Try again when the timer ends.",
        headers={"Retry-After": str(retry_after)},
    )


def authenticate(
    form_data: OAuth2PasswordRequestForm, client_id: str | None = None
) -> Principal:
    key = (form_data.username.lower(), client_id)
    if client_id is not None:
        now = _monotonic()
        with _login_attempts_lock:
            expired_keys = [
                attempt_key
                for attempt_key, (_, locked, last_attempt) in _login_attempts.items()
                if now - last_attempt >= LOGIN_ATTEMPT_WINDOW_SECONDS
                and (locked is None or now >= locked)
            ]
            for attempt_key in expired_keys:
                _login_attempts.pop(attempt_key, None)

            _, locked_until, _ = _login_attempts.get(key, (0, None, now))
            # Checked before the password so a locked account cannot be probed.
            if locked_until is not None and now < locked_until:
                raise _lockout_exception(max(1, int(locked_until - now + 0.999)))

    credentials = _find_credentials(form_data.username)
    if credentials is None:
        _verify_unknown_user(form_data.password)
        valid_credentials = False
    else:
        valid_credentials = _password_matches(form_data.password, credentials[1])

    if client_id is not None:
        now = _monotonic()
        with _login_attempts_lock:
            failures, locked_until, last_attempt = _login_attempts.get(
                key, (0, None, now)
            )
            if locked_until is not None:
                failures = 0
            if now - last_attempt >= LOGIN_ATTEMPT_WINDOW_SECONDS:
                failures = 0
            if valid_credentials:
                _login_attempts.pop(key, None)
            else:
                failures += 1
                if failures >= LOGIN_MAX_ATTEMPTS:
                    _login_attempts[key] = (0, now + LOGIN_LOCKOUT_SECONDS, now)
                    raise _lockout_exception(LOGIN_LOCKOUT_SECONDS)
                _login_attempts[key] = (failures, None, now)

    if not valid_credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Principal(username=credentials[0], role=credentials[2])


def register_user(
    username: str, password: str, client_id: str | None = None
) -> Principal:
    """Create a viewer account after checking the username and password policy."""
    if not REGISTRATION_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is disabled.",
        )

    if client_id is not None and REGISTRATION_MAX_PER_CLIENT > 0:
        now = _monotonic()
        with _registrations_lock:
            attempts = _registrations.setdefault(client_id, deque())
            while attempts and now - attempts[0] >= REGISTRATION_WINDOW_SECONDS:
                attempts.popleft()
            if len(attempts) >= REGISTRATION_MAX_PER_CLIENT:
                retry_after = max(
                    1, int(REGISTRATION_WINDOW_SECONDS - (now - attempts[0]))
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many registration attempts from this connection. Try again later.",
                    headers={"Retry-After": str(retry_after)},
                )
            attempts.append(now)

    problem = users.username_problem(username) or users.password_problem(
        password, username
    )
    if problem:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=problem)

    taken = HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="That username is not available.",
    )
    if any(existing.lower() == username.lower() for existing in AUTH_USERS):
        raise taken
    try:
        users.create_user(username, password, ROLE_VIEWER)
    except users.UsernameTakenError:
        raise taken from None
    return Principal(username=username, role=ROLE_VIEWER)


def get_role_for_username(username: str) -> str:
    credentials = _find_credentials(username)
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unknown user",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials[2]


def get_trusted_origins() -> list[str]:
    return [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            # Port 8081 is the Expo web dev server (mobile/).
            "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8081,http://127.0.0.1:8081",
        ).split(",")
        if origin.strip()
    ]


def _is_trusted_origin(request: Request) -> bool:
    """Block cross-site writes that ride on the browser's auth cookie (CSRF)."""
    headers = getattr(request, "headers", None) or {}
    source = headers.get("origin") or headers.get("referer")
    if not source:
        return True
    parts = urlsplit(source)
    if parts.netloc and parts.netloc == headers.get("host"):
        return True
    return f"{parts.scheme}://{parts.netloc}" in get_trusted_origins()


def _decode_access_token(token: str) -> Principal:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        claims = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "exp", "role"]},
        )
        if claims.get("type", "access") != "access":
            raise credentials_exception
        if not isinstance(claims["sub"], str) or claims.get("role") not in VALID_ROLES:
            raise credentials_exception
        if _issued_before_revocation(claims):
            raise credentials_exception
        return Principal(username=claims["sub"], role=claims["role"])
    except (InvalidTokenError, KeyError, TypeError):
        raise credentials_exception from None


def get_current_principal(
    bearer_token: str | None = _oauth2_dependency,
    request: Request = None,
) -> Principal:
    token = bearer_token or (request.cookies.get(AUTH_COOKIE_NAME) if request else None)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if (
        bearer_token is None
        and getattr(request, "method", "GET") not in SAFE_METHODS
        and not _is_trusted_origin(request)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-site request blocked",
        )
    return _decode_access_token(token)


_current_principal_dependency = Depends(get_current_principal)


def get_current_user(
    bearer_token: str | None = _oauth2_dependency,
    request: Request = None,
) -> str:
    return get_current_principal(bearer_token, request).username


def require_role(*allowed_roles: str):
    """Dependency factory: restrict a route to principals with one of the given roles."""

    def dependency(principal: Principal = _current_principal_dependency) -> Principal:
        if principal.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return principal

    return dependency


require_admin = require_role(ROLE_ADMIN)


def require_permission(permission: str):
    """Allow administrators or users granted the named capability."""

    def dependency(principal: Principal = _current_principal_dependency) -> Principal:
        if principal.role == ROLE_ADMIN:
            return principal
        with closing(database.get_connection()) as connection:
            granted = connection.execute(
                "SELECT 1 FROM user_permissions WHERE username = ? AND permission = ?",
                (principal.username, permission),
            ).fetchone()
        if granted is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return principal

    return dependency


def _refresh_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def decode_refresh_token(token: str | None) -> dict:
    """Check a refresh token's signature, type and expiry, and return its claims.

    This does not look at the database; rotate_refresh_token() also checks that the
    token has not been used or revoked.
    """
    if token is None:
        raise _refresh_exception()
    try:
        claims = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "exp", "type", "jti", "fam"]},
        )
        if claims["type"] != "refresh" or not isinstance(claims["sub"], str):
            raise _refresh_exception()
        if not isinstance(claims["jti"], str) or not isinstance(claims["fam"], str):
            raise _refresh_exception()
        if _issued_before_revocation(claims):
            raise _refresh_exception()
        return claims
    except (InvalidTokenError, KeyError, TypeError):
        raise _refresh_exception() from None


def refresh_token_from_request(
    bearer_token: str | None = _refresh_token_dependency,
    request: Request = None,
) -> str | None:
    """API clients send the refresh token as a Bearer token; the web build sends its cookie."""
    if bearer_token:
        return bearer_token
    token = request.cookies.get(REFRESH_COOKIE_NAME) if request else None
    if token and not _is_trusted_origin(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-site request blocked",
        )
    return token


def rotate_refresh_token(token: str | None) -> tuple[str, str]:
    """Spend a refresh token and return (username, its replacement).

    A refresh token works once. Presenting one that was already rotated or revoked
    means it may have been copied, so the whole sign-in (its family) is revoked.
    """
    claims = decode_refresh_token(token)
    now = int(time.time())
    with closing(database.get_connection()) as connection:
        row = connection.execute(
            "SELECT username FROM refresh_tokens WHERE jti = ? AND family_id = ?",
            (claims["jti"], claims["fam"]),
        ).fetchone()
        spent = connection.execute(
            """
            UPDATE refresh_tokens SET used_at = ?
            WHERE jti = ? AND family_id = ? AND used_at IS NULL AND revoked_at IS NULL
            """,
            (now, claims["jti"], claims["fam"]),
        ).rowcount
        if spent != 1:
            if row is not None:
                logger.warning(
                    "A rotated or revoked refresh token was presented; ending that sign-in."
                )
                connection.execute(
                    "UPDATE refresh_tokens SET revoked_at = ? WHERE family_id = ? AND revoked_at IS NULL",
                    (now, claims["fam"]),
                )
                connection.commit()
            raise _refresh_exception()

        connection.execute("DELETE FROM refresh_tokens WHERE expires_at < ?", (now,))
        username = row[0]
        replacement = _new_refresh_token(connection, username, claims["fam"])
        connection.commit()
    return username, replacement


def revoke_refresh_token(token: str | None, username: str) -> None:
    """End one sign-in (the family of this refresh token) if it belongs to the user.

    Invalid or foreign tokens are ignored, so signing out always succeeds.
    """
    try:
        claims = decode_refresh_token(token)
    except HTTPException:
        return
    if claims["sub"].lower() != username.lower():
        return
    with closing(database.get_connection()) as connection:
        connection.execute(
            "UPDATE refresh_tokens SET revoked_at = ? WHERE family_id = ? AND revoked_at IS NULL",
            (int(time.time()), claims["fam"]),
        )
        connection.commit()


def refresh_session(response, token: str | None) -> dict[str, str]:
    """Rotate a refresh token, set fresh cookies, and return the new token pair."""
    username, refresh_token = rotate_refresh_token(token)
    access_token = create_access_token(username, get_role_for_username(username))
    _set_auth_cookies(response, access_token, refresh_token)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",  # a token type, not a secret  # nosec B105
    }
