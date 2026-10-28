"""The signed-in user's own profile page: view and edit it, and see their wishlist.

Profiles are the same records administrators edit in the user directory
(routes/admin/users.py), so changes made in either place show up in both.
"""

from contextlib import closing

from fastapi import APIRouter, Depends
from pydantic import Field

from backend.auth.auth import Principal, get_current_principal
from backend.database.database import get_connection
from routes.admin.users import (
    FAVORITE_GAMES_MAX,
    GAME_SUMMARY_COLUMNS,
    ProfileUpdate,
    game_summary,
    get_profile,
    save_profile,
)

router = APIRouter(prefix="/users/me/profile", tags=["users"])


class OwnProfileUpdate(ProfileUpdate):
    # Leaving favorites out keeps them; the library adds favorites one at a time.
    favorite_game_ids: list[int] | None = Field(default=None, max_length=FAVORITE_GAMES_MAX)


def _own_profile(username: str) -> dict:
    with closing(get_connection()) as connection:
        wishlist = connection.execute(
            f"""
            SELECT {GAME_SUMMARY_COLUMNS}
            FROM user_wishlist_games w JOIN games g ON g.id = w.game_id
            WHERE w.username = ?
            ORDER BY w.added_at, g.id
            """,  # constant column list  # nosec B608
            (username,),
        ).fetchall()
    return {
        **get_profile(username),
        "wishlist_games": [game_summary(row) for row in wishlist],
        "favorites_max": FAVORITE_GAMES_MAX,
    }


@router.get("")
def get_my_profile(principal: Principal = Depends(get_current_principal)) -> dict:
    return _own_profile(principal.username)


@router.put("")
def update_my_profile(
    body: OwnProfileUpdate, principal: Principal = Depends(get_current_principal)
) -> dict:
    save_profile(principal.username, body)
    return _own_profile(principal.username)
