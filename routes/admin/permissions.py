"""Administrator-managed capabilities for individual accounts."""

from contextlib import closing

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam, status
from pydantic import BaseModel, Field, field_validator

from backend.auth import auth
from backend.access.permissions import PERMISSIONS
from backend.database.database import get_connection
from routes.admin.users import USERNAME_PATH_PATTERN, _accounts

router = APIRouter(
    prefix="/admin/permissions/api",
    tags=["admin"],
    dependencies=[Depends(auth.require_admin)],
)


class PermissionUpdate(BaseModel):
    permissions: list[str] = Field(max_length=len(PERMISSIONS))

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("Each permission may only be selected once.")
        unknown = set(values) - PERMISSIONS.keys()
        if unknown:
            raise ValueError(f"Unknown permission(s): {', '.join(sorted(unknown))}.")
        return values


def _account(username: str) -> dict:
    account = _accounts().get(username.lower())
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return account


@router.get("")
def list_permissions() -> dict:
    accounts = sorted(
        _accounts().values(),
        key=lambda item: (item["role"] != auth.ROLE_ADMIN, item["username"].lower()),
    )
    with closing(get_connection()) as connection:
        grants = connection.execute(
            "SELECT username, permission FROM user_permissions ORDER BY username, permission"
        ).fetchall()
    by_user: dict[str, list[str]] = {}
    for grant in grants:
        by_user.setdefault(grant["username"].lower(), []).append(grant["permission"])
    return {
        "permissions": [{"key": key, **value} for key, value in PERMISSIONS.items()],
        "users": [
            {**account, "permissions": by_user.get(account["username"].lower(), [])}
            for account in accounts
        ],
    }


@router.put("/{username}")
def update_permissions(
    body: PermissionUpdate,
    username: str = PathParam(pattern=USERNAME_PATH_PATTERN),
) -> dict:
    account = _account(username)
    with closing(get_connection()) as connection:
        connection.execute("DELETE FROM user_permissions WHERE username = ?", (account["username"],))
        connection.executemany(
            "INSERT INTO user_permissions (username, permission) VALUES (?, ?)",
            [(account["username"], permission) for permission in body.permissions],
        )
        connection.commit()
    return {"username": account["username"], "permissions": body.permissions}
