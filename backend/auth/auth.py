import os
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jwt.exceptions import InvalidTokenError

TOKEN_EXPIRE_SECONDS = int(os.getenv("TOKEN_EXPIRE_SECONDS", "1800"))
REFRESH_TOKEN_EXPIRE_SECONDS = int(
    os.getenv("REFRESH_TOKEN_EXPIRE_SECONDS", "604800")
)
AUTH_COOKIE_NAME = os.getenv("AUTH_COOKIE_NAME", "access_token")
AUTH_COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "false").lower() == "true"
JWT_SECRET = os.getenv("JWT_SECRET", "change-this-secret-in-production")
JWT_ALGORITHM = "HS256"
AUTH_USERNAME = os.getenv("AUTH_USERNAME", "admin")
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "1234")
LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", "3"))
LOGIN_LOCKOUT_SECONDS = int(os.getenv("LOGIN_LOCKOUT_SECONDS", "60"))
LOGIN_ATTEMPT_WINDOW_SECONDS = int(os.getenv("LOGIN_ATTEMPT_WINDOW_SECONDS", "300"))

ROLE_ADMIN = "admin"
ROLE_VIEWER = "viewer"
VALID_ROLES = {ROLE_ADMIN, ROLE_VIEWER}


def _load_users() -> dict[str, tuple[str, str]]:
    """Return {username: (password, role)}.

    Configured via AUTH_USERS="user:password:role,user2:password2:role2".
    Falls back to a single admin user from AUTH_USERNAME/AUTH_PASSWORD.
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
_monotonic = time.monotonic

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)
refresh_token_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


@dataclass(frozen=True)
class Principal:
    username: str
    role: str


def _create_token(
    username: str, token_type: str, expires_in: int, role: str | None = None
) -> str:
    claims = {
        "sub": username,
        "type": token_type,
        "exp": datetime.now(timezone.utc) + timedelta(seconds=expires_in),
    }
    if role is not None:
        claims["role"] = role
    return jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_access_token(username: str, role: str) -> str:
    return _create_token(username, "access", TOKEN_EXPIRE_SECONDS, role=role)


def create_refresh_token(username: str) -> str:
    return _create_token(username, "refresh", REFRESH_TOKEN_EXPIRE_SECONDS)


def authenticate(
    form_data: OAuth2PasswordRequestForm, client_id: str | None = None
) -> Principal:
    credentials = AUTH_USERS.get(form_data.username)
    valid_credentials = credentials is not None and secrets.compare_digest(
        form_data.password, credentials[0]
    )

    if client_id is not None:
        key = (form_data.username, client_id)
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

            failures, locked_until, last_attempt = _login_attempts.get(
                key, (0, None, now)
            )
            if locked_until is not None and now < locked_until:
                retry_after = max(1, int(locked_until - now + 0.999))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Login locked after {LOGIN_MAX_ATTEMPTS} failed attempts. Try again when the timer ends.",
                    headers={"Retry-After": str(retry_after)},
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
                    locked_until = now + LOGIN_LOCKOUT_SECONDS
                    _login_attempts[key] = (0, locked_until, now)
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=f"Login locked after {LOGIN_MAX_ATTEMPTS} failed attempts. Try again when the timer ends.",
                        headers={"Retry-After": str(LOGIN_LOCKOUT_SECONDS)},
                    )
                _login_attempts[key] = (failures, None, now)

    if not valid_credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Principal(username=form_data.username, role=credentials[1])


def get_role_for_username(username: str) -> str:
    credentials = AUTH_USERS.get(username)
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unknown user",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials[1]


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
        return Principal(username=claims["sub"], role=claims["role"])
    except (InvalidTokenError, KeyError, TypeError):
        raise credentials_exception from None


def get_current_principal(
    bearer_token: str | None = Depends(oauth2_scheme),
    request: Request = None,
) -> Principal:
    token = bearer_token or (request.cookies.get(AUTH_COOKIE_NAME) if request else None)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _decode_access_token(token)


def get_current_user(
    bearer_token: str | None = Depends(oauth2_scheme),
    request: Request = None,
) -> str:
    return get_current_principal(bearer_token, request).username


def require_role(*allowed_roles: str):
    """Dependency factory: restrict a route to principals with one of the given roles."""

    def dependency(principal: Principal = Depends(get_current_principal)) -> Principal:
        if principal.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return principal

    return dependency


require_admin = require_role(ROLE_ADMIN)


def get_current_user_from_refresh_token(
    token: str | None = Depends(refresh_token_scheme),
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
        return claims["sub"]
    except (InvalidTokenError, KeyError, TypeError):
        raise credentials_exception from None