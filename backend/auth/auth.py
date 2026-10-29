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
AUTH_COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "false").lower() == "true"
# Without a configured secret, sign with a random per-process key rather than a
# well-known one; tokens then stop working whenever the app restarts.
JWT_SECRET = os.getenv("JWT_SECRET") or secrets.token_urlsafe(32)
JWT_ALGORITHM = "HS256"
AUTH_USERNAME = os.getenv("AUTH_USERNAME", "admin")
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "1234")
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
    Falls back to a single admin user from AUTH_USERNAME/AUTH_PASSWORD.
    A password may also be a hash from `python -m backend.auth.users hash`.
    """
    raw = os.getenv("AUTH_USERS")
    if not raw:
        return {AUTH_USERNAME: (AUTH_PASSWORD, ROLE_ADMIN)}

    users: dict[str, tuple[str, str]] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        username, password, role = entry.split(":")
        if role not in VALID_ROLES:
            raise ValueError(f"Invalid role {role!r} for user {username!r}")
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
    username: str, token_type: str, expires_in: int, role: str | None = None
) -> str:
    claims = {
        "iat": datetime.now(UTC),
        "jti": secrets.token_urlsafe(12),
        "sub": username,
        "type": token_type,
        "exp": datetime.now(UTC) + timedelta(seconds=expires_in),
    }
    if role is not None:
        claims["role"] = role
    return jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_access_token(username: str, role: str) -> str:
    return _create_token(username, "access", TOKEN_EXPIRE_SECONDS, role=role)


def create_refresh_token(username: str) -> str:
    return _create_token(username, "refresh", REFRESH_TOKEN_EXPIRE_SECONDS)


def issue_session(response, principal: Principal) -> dict[str, str]:
    """Set the auth cookie on a response and return the token pair for API clients."""
    token = create_access_token(principal.username, principal.role)
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        max_age=TOKEN_EXPIRE_SECONDS,
        httponly=True,
        secure=AUTH_COOKIE_SECURE,
        samesite="lax",
    )
    return {
        "access_token": token,
        "refresh_token": create_refresh_token(principal.username),
        "token_type": "bearer",  # a token type, not a secret  # nosec B105
    }


def sessions_valid_after(username: str) -> int:
    """Epoch second before which this user's tokens are no longer accepted."""
    if not os.path.exists(database.DATABASE_PATH):
        return 0
    try:
        with closing(database.get_connection()) as connection:
            row = connection.execute(
                "SELECT sessions_valid_after FROM user_security WHERE username = ?", (username,)
            ).fetchone()
    except sqlite3.OperationalError:
        return 0
    return row[0] if row else 0


def revoke_sessions(username: str) -> None:
    """Sign a user out everywhere: tokens issued before now stop working."""
    with closing(database.get_connection()) as connection:
        connection.execute(
            """
            INSERT INTO user_security (username, sessions_valid_after) VALUES (?, ?)
            ON CONFLICT (username) DO UPDATE SET sessions_valid_after = excluded.sessions_valid_after
            """,
            (username, int(time.time())),
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
            "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
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


def get_current_user_from_refresh_token(
    token: str | None = _refresh_token_dependency,
) -> str:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise credentials_exception

    try:
        claims = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "exp", "type"]},
        )
        if claims["type"] != "refresh" or not isinstance(claims["sub"], str):
            raise credentials_exception
        if _issued_before_revocation(claims):
            raise credentials_exception
        return claims["sub"]
    except (InvalidTokenError, KeyError, TypeError):
        raise credentials_exception from None