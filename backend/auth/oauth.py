"""OpenID Connect clients and local account provisioning for social sign-in."""

import hashlib
import os
import secrets
from contextlib import closing
from datetime import UTC, datetime

from authlib.integrations.starlette_client import OAuth

from backend.auth import auth, users
from backend.database import database

SESSION_SECRET = os.getenv("OAUTH_SESSION_SECRET") or auth.JWT_SECRET
MICROSOFT_TENANT = os.getenv("OAUTH_MICROSOFT_TENANT", "common")

oauth = OAuth()

if os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"):
    oauth.register(
        name="google",
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        server_metadata_url=(
            "https://accounts.google.com/"
            ".well-known/openid-configuration"
        ),
        client_kwargs={"scope": "openid email profile"},
    )

if os.getenv("MICROSOFT_CLIENT_ID") and os.getenv("MICROSOFT_CLIENT_SECRET"):
    oauth.register(
        name="microsoft",
        client_id=os.environ["MICROSOFT_CLIENT_ID"],
        client_secret=os.environ["MICROSOFT_CLIENT_SECRET"],
        server_metadata_url=(
            "https://login.microsoftonline.com/"
            f"{MICROSOFT_TENANT}/v2.0/.well-known/openid-configuration"
        ),
        client_kwargs={"scope": "openid email profile"},
    )


class OAuthLoginError(Exception):
    """The provider identity could not be used to sign in."""


def get_client(provider: str):
    if provider not in {"google", "microsoft"}:
        return None
    return oauth.create_client(provider)


def available_providers() -> list[dict[str, str]]:
    return [
        {"id": provider, "name": name}
        for provider, name in (
            ("google", "Google"),
            ("microsoft", "Microsoft"),
        )
        if get_client(provider) is not None
    ]


def _new_username(provider: str, subject: str) -> str:
    identity = f"{provider}\0{subject}".encode("utf-8")
    identity_hash = hashlib.sha256(identity).hexdigest()
    return f"oauth_{identity_hash[:26]}"


def get_or_create_principal(
    provider: str, userinfo: dict
) -> auth.Principal:
    subject = userinfo.get("sub")
    if not isinstance(subject, str) or not subject:
        raise OAuthLoginError(
            "The provider did not return a valid identity."
        )

    email = userinfo.get("email")
    display_name = userinfo.get("name") or userinfo.get("preferred_username")
    email = email.strip().lower() if isinstance(email, str) else None
    display_name = (
        display_name.strip() if isinstance(display_name, str) else None
    )
    username = _new_username(provider, subject)

    with closing(database.get_connection()) as connection:
        identity = connection.execute(
            """
            SELECT username FROM oauth_identities
            WHERE provider = ? AND subject = ?
            """,
            (provider, subject),
        ).fetchone()
        if identity:
            row = connection.execute(
                "SELECT role FROM users WHERE username = ?",
                (identity["username"],),
            ).fetchone()
            if row:
                if email or display_name:
                    connection.execute(
                        """
                            INSERT INTO user_profiles (
                                username, email, display_name, updated_at
                            )
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT (username) DO UPDATE SET
                            email = COALESCE(
                                excluded.email, user_profiles.email
                            ),
                            display_name = COALESCE(
                                excluded.display_name,
                                user_profiles.display_name
                            ),
                            updated_at = excluded.updated_at
                        """,
                        (
                            identity["username"],
                            email,
                            display_name,
                            datetime.now(UTC).isoformat(),
                        ),
                    )
                    connection.commit()
                return auth.Principal(
                    identity["username"], row["role"]
                )

        if not auth.REGISTRATION_ENABLED:
            raise OAuthLoginError("New account registration is disabled.")

        occupied = connection.execute(
            "SELECT 1 FROM users WHERE username = ? COLLATE NOCASE",
            (username,),
        ).fetchone()
        configured_username = any(
            name.lower() == username.lower() for name in auth.AUTH_USERS
        )
        if occupied or configured_username:
            raise OAuthLoginError(
                "Could not create an account for this identity."
            )

        connection.execute(
            """
            INSERT INTO users (username, password_hash, role, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                username,
                users.hash_password(secrets.token_urlsafe(48)),
                auth.ROLE_VIEWER,
                datetime.now(UTC).isoformat(timespec="seconds"),
            ),
        )
        connection.execute(
            """
            INSERT INTO oauth_identities (provider, subject, username)
            VALUES (?, ?, ?)
            """,
            (provider, subject, username),
        )
        connection.execute(
            """
            INSERT INTO user_profiles (
                username, email, display_name, updated_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                username,
                email,
                display_name,
                datetime.now(UTC).isoformat(),
            ),
        )
        connection.commit()

    return auth.Principal(username, auth.ROLE_VIEWER)
