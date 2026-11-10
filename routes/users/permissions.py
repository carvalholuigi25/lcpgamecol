"""Self-service access to capabilities and permitted profile editing."""

from contextlib import closing

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam, status
from pydantic import BaseModel, Field, field_validator

from backend.access.permissions import ALL_PERMISSIONS
from backend.auth import auth
from backend.auth.auth import Principal, get_current_principal, require_permission
from backend.database.database import get_connection
from routes.admin.users import (
    FAVORITE_GAMES_MAX,
    USERNAME_PATH_PATTERN,
    ProfileUpdate,
    _accounts,
    _profiles,
    get_profile,
    save_profile,
    validate_image_url,
)

router = APIRouter(tags=["permissions"])


class ManagedProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=64)
    bio: str | None = Field(default=None, max_length=600)
    location: str | None = Field(default=None, max_length=80)
    avatar_url: str | None = None
    cover_url: str | None = None
    favorite_game_ids: list[int] | None = Field(default=None, max_length=FAVORITE_GAMES_MAX)

    @field_validator("display_name", "bio", "location")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return (value or "").strip() or None

    @field_validator("avatar_url", "cover_url")
    @classmethod
    def check_image_url(cls, value: str | None) -> str | None:
        return validate_image_url(value)


def _manageable_profile(username: str) -> dict:
    profile = get_profile(username)
    return {
        **{
            key: profile[key]
            for key in ("username", "display_name", "bio", "location", "avatar_url", "cover_url")
        },
        "favorite_game_ids": [game["id"] for game in profile["favorite_games"]],
    }


@router.get("/users/me/permissions")
def get_my_permissions(principal: Principal = Depends(get_current_principal)) -> dict:
    if principal.role == auth.ROLE_ADMIN:
        permissions = list(ALL_PERMISSIONS)
    else:
        with closing(get_connection()) as connection:
            rows = connection.execute(
                "SELECT permission FROM user_permissions WHERE username = ? ORDER BY permission",
                (principal.username,),
            ).fetchall()
        permissions = [row["permission"] for row in rows]
    return {"username": principal.username, "role": principal.role, "permissions": permissions}


@router.get("/users/manageable")
def list_manageable_users(
    _principal: Principal = Depends(require_permission("users.edit_profile")),
) -> list[dict]:
    users = sorted(_accounts().values(), key=lambda account: account["username"].lower())
    profiles = {
        profile["username"].lower(): profile
        for profile in _profiles([user["username"] for user in users])
    }
    return [
        {
            "username": user["username"],
            "display_name": profiles[user["username"].lower()]["display_name"],
        }
        for user in users
    ]


@router.get("/users/manageable/{username}")
def get_manageable_user(
    username: str = PathParam(pattern=USERNAME_PATH_PATTERN),
    _principal: Principal = Depends(require_permission("users.edit_profile")),
) -> dict:
    if username.lower() not in _accounts():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return _manageable_profile(username)


@router.put("/users/manageable/{username}")
def update_manageable_user(
    body: ManagedProfileUpdate,
    username: str = PathParam(pattern=USERNAME_PATH_PATTERN),
    _principal: Principal = Depends(require_permission("users.edit_profile")),
) -> dict:
    account = _accounts().get(username.lower())
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    current = get_profile(account["username"])
    save_profile(
        account["username"],
        ProfileUpdate(
            display_name=body.display_name if "display_name" in body.model_fields_set else current["display_name"],
            bio=body.bio if "bio" in body.model_fields_set else current["bio"],
            location=body.location if "location" in body.model_fields_set else current["location"],
            avatar_url=body.avatar_url if "avatar_url" in body.model_fields_set else current["avatar_url"],
            cover_url=body.cover_url if "cover_url" in body.model_fields_set else current["cover_url"],
            email=current["email"],
            favorite_game_ids=(
                body.favorite_game_ids
                if "favorite_game_ids" in body.model_fields_set
                else [game["id"] for game in current["favorite_games"]]
            ),
        ),
    )
    return _manageable_profile(account["username"])
