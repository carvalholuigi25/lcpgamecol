"""User directory for administrators: every account with its profile and favorite games.

Accounts come from two places: AUTH_USERS (configured in the environment) and the
users table (self-registered). Profiles and favorites are stored by username so
both kinds of account can have one.
"""

import re
from contextlib import closing
from datetime import UTC, datetime
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, status
from fastapi import Path as PathParam
from pydantic import BaseModel, Field, field_validator

from backend.auth import auth
from backend.database.database import get_connection
from backend.realtime.hub import hub

FAVORITE_GAMES_MAX = 12
IMAGE_URL_MAX_LENGTH = 2048
USERNAME_PATH_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.@-]{0,63}$"
UPLOAD_IMAGE_PATTERN = re.compile(r"^/admin/uploads/[0-9a-f]{32}(\?inline=true)?$")

router = APIRouter(prefix="/admin/users", tags=["admin"])


def validate_image_url(value: str | None) -> str | None:
    """Allow http(s) links, the app's own public images, and uploaded images only."""
    value = (value or "").strip()
    if not value:
        return None
    if len(value) > IMAGE_URL_MAX_LENGTH:
        raise ValueError(f"Image links must be {IMAGE_URL_MAX_LENGTH} characters or fewer.")
    if UPLOAD_IMAGE_PATTERN.fullmatch(value) or (
        value.startswith("/public/") and ".." not in value and "\\" not in value
    ):
        return value
    parts = urlsplit(value)
    if parts.scheme in ("http", "https") and parts.netloc:
        return value
    raise ValueError("Use an http(s) image link, a /public/ image, or an uploaded image.")


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=64)
    bio: str | None = Field(default=None, max_length=600)
    location: str | None = Field(default=None, max_length=80)
    avatar_url: str | None = None
    cover_url: str | None = None
    favorite_game_ids: list[int] = Field(default_factory=list, max_length=FAVORITE_GAMES_MAX)

    @field_validator("display_name", "bio", "location")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return (value or "").strip() or None

    @field_validator("avatar_url", "cover_url")
    @classmethod
    def check_image_url(cls, value: str | None) -> str | None:
        return validate_image_url(value)

    @field_validator("favorite_game_ids")
    @classmethod
    def unique_ids(cls, value: list[int] | None) -> list[int] | None:
        return None if value is None else list(dict.fromkeys(value))


def _accounts() -> dict[str, dict]:
    """Return {lowercase username: account} for configured and registered users."""
    accounts = {
        username.lower(): {"username": username, "role": role, "source": "configured", "created_at": None}
        for username, (_password, role) in auth.AUTH_USERS.items()
    }
    with closing(get_connection()) as connection:
        rows = connection.execute("SELECT username, role, created_at FROM users ORDER BY created_at, id").fetchall()
    for row in rows:
        # A configured account wins when both share a name, as it does at sign-in.
        accounts.setdefault(
            row["username"].lower(),
            {"username": row["username"], "role": row["role"], "source": "registered", "created_at": row["created_at"]},
        )
    return accounts


GAME_SUMMARY_COLUMNS = (
    "g.id, g.title, g.genre, g.release_year, g.platforms, "
    "g.cover_image_url, g.image_url, g.user_rating, g.hoursplayed"
)


def game_summary(row) -> dict:
    """Shape a row selected with GAME_SUMMARY_COLUMNS for profile pages."""
    return {
        "id": row["id"],
        "title": row["title"],
        "genre": row["genre"],
        "release_year": row["release_year"],
        "platforms": row["platforms"],
        "cover_image_url": row["cover_image_url"] or row["image_url"] or None,
        "user_rating": row["user_rating"] or 0,
        "hours_played": row["hoursplayed"] or 0,
    }


def _profiles(usernames: list[str]) -> list[dict]:
    if not usernames:
        return []
    keys = [username.lower() for username in usernames]
    placeholders = ", ".join("?" for _ in keys)
    with closing(get_connection()) as connection:
        profiles = {
            row["username"].lower(): row
            for row in connection.execute(
                f"SELECT * FROM user_profiles WHERE lower(username) IN ({placeholders})", keys  # only ? placeholders are interpolated  # nosec B608
            )
        }
        favorites: dict[str, list[dict]] = {}
        for row in connection.execute(
            f"""
            SELECT f.username, {GAME_SUMMARY_COLUMNS}
            FROM user_favorite_games f JOIN games g ON g.id = f.game_id
            WHERE lower(f.username) IN ({placeholders})
            ORDER BY f.position, g.title
            """,  # constant columns and ? placeholders only  # nosec B608
            keys,
        ):
            favorites.setdefault(row["username"].lower(), []).append(game_summary(row))

    accounts = _accounts()
    results = []
    for key in keys:
        account = accounts[key]
        profile = profiles.get(key)
        favorite_games = favorites.get(key, [])
        results.append(
            {
                **account,
                "display_name": profile["display_name"] if profile else None,
                "bio": profile["bio"] if profile else None,
                "location": profile["location"] if profile else None,
                "avatar_url": profile["avatar_url"] if profile else None,
                "cover_url": profile["cover_url"] if profile else None,
                "updated_at": profile["updated_at"] if profile else None,
                "favorite_games": favorite_games,
                "hours_in_favorites": round(sum(float(game["hours_played"]) for game in favorite_games), 1),
            }
        )
    return results


def get_profile(username: str) -> dict:
    return _profiles([username])[0]


def _get_account(username: str) -> dict:
    account = _accounts().get(username.lower())
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return account


@router.get("")
def list_users() -> list[dict]:
    accounts = _accounts()
    ordered = sorted(accounts.values(), key=lambda account: (account["role"] != auth.ROLE_ADMIN, account["username"].lower()))
    return _profiles([account["username"] for account in ordered])


@router.get("/game-options")
def list_favorite_game_options() -> list[dict]:
    with closing(get_connection()) as connection:
        rows = connection.execute("SELECT id, title, release_year FROM games ORDER BY title COLLATE NOCASE").fetchall()
    return [{"id": row["id"], "title": row["title"], "release_year": row["release_year"]} for row in rows]


@router.get("/{username}")
def get_user_profile(username: str = PathParam(pattern=USERNAME_PATH_PATTERN)) -> dict:
    return get_profile(_get_account(username)["username"])


def save_profile(username: str, body: ProfileUpdate) -> dict:
    """Store the profile of an existing account and return it.

    A favorite_game_ids of None keeps the current favorites.
    """
    account = _get_account(username)
    favorite_ids = body.favorite_game_ids
    with closing(get_connection()) as connection:
        if favorite_ids:
            placeholders = ", ".join("?" for _ in favorite_ids)
            found = {
                row[0]
                for row in connection.execute(
                    f"SELECT id FROM games WHERE id IN ({placeholders})", favorite_ids  # only ? placeholders are interpolated  # nosec B608
                )
            }
            missing = [game_id for game_id in favorite_ids if game_id not in found]
            if missing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unknown game id(s): {', '.join(map(str, missing))}",
                )

        connection.execute(
            """
            INSERT INTO user_profiles (username, display_name, bio, location, avatar_url, cover_url, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (username) DO UPDATE SET
                display_name = excluded.display_name, bio = excluded.bio,
                location = excluded.location, avatar_url = excluded.avatar_url,
                cover_url = excluded.cover_url, updated_at = excluded.updated_at
            """,
            (
                account["username"], body.display_name, body.bio, body.location,
                body.avatar_url, body.cover_url,
                datetime.now(UTC).isoformat(timespec="seconds"),
            ),
        )
        if favorite_ids is not None:
            connection.execute("DELETE FROM user_favorite_games WHERE username = ?", (account["username"],))
            connection.executemany(
                "INSERT INTO user_favorite_games (username, game_id, position) VALUES (?, ?, ?)",
                [(account["username"], game_id, position) for position, game_id in enumerate(favorite_ids)],
            )
        connection.commit()
    if favorite_ids is not None:
        hub.publish("listsChanged", {"game_id": None}, username=account["username"])
    return get_profile(account["username"])


@router.put("/{username}")
def update_user_profile(
    body: ProfileUpdate, username: str = PathParam(pattern=USERNAME_PATH_PATTERN)
) -> dict:
    return save_profile(username, body)
