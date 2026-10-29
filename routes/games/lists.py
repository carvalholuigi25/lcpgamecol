"""Each signed-in user's own wishlist and favorite games.

Favorites share the user_favorite_games table with the admin user directory, so a
pick made from the library shows up on the user's profile and the other way round.
"""

from contextlib import closing
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from backend.auth.auth import Principal, get_current_principal
from backend.database.database import get_connection
from backend.realtime.hub import hub
from routes.admin.users import FAVORITE_GAMES_MAX

router = APIRouter(tags=["user lists"])
CURRENT_PRINCIPAL = Depends(get_current_principal)


def _require_game(connection, game_id: int) -> None:
    if connection.execute("SELECT 1 FROM games WHERE id = ?", (game_id,)).fetchone() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")


def _list_state(connection, username: str, game_id: int) -> dict:
    wishlisted = connection.execute(
        "SELECT 1 FROM user_wishlist_games WHERE username = ? AND game_id = ?",
        (username, game_id),
    ).fetchone()
    favorite = connection.execute(
        "SELECT 1 FROM user_favorite_games WHERE username = ? AND game_id = ?",
        (username, game_id),
    ).fetchone()
    return {"game_id": game_id, "wishlisted": bool(wishlisted), "favorite": bool(favorite)}


def _changed(connection, principal: Principal, game_id: int) -> dict:
    connection.commit()
    state = _list_state(connection, principal.username, game_id)
    hub.publish("listsChanged", state, username=principal.username)
    return state


@router.get("/users/me/game-lists")
def get_my_game_lists(principal: Principal = CURRENT_PRINCIPAL) -> dict:
    with closing(get_connection()) as connection:
        wishlist = connection.execute(
            "SELECT game_id FROM user_wishlist_games WHERE username = ? ORDER BY added_at, game_id",
            (principal.username,),
        ).fetchall()
        favorites = connection.execute(
            "SELECT game_id FROM user_favorite_games WHERE username = ? ORDER BY position, game_id",
            (principal.username,),
        ).fetchall()
    return {
        "wishlist": [row["game_id"] for row in wishlist],
        "favorites": [row["game_id"] for row in favorites],
        "favorites_max": FAVORITE_GAMES_MAX,
    }


@router.put("/games/{game_id}/wishlist")
def add_to_wishlist(game_id: int, principal: Principal = CURRENT_PRINCIPAL) -> dict:
    with closing(get_connection()) as connection:
        _require_game(connection, game_id)
        connection.execute(
            "INSERT OR IGNORE INTO user_wishlist_games (username, game_id, added_at) VALUES (?, ?, ?)",
            (principal.username, game_id, datetime.now(UTC).isoformat(timespec="seconds")),
        )
        return _changed(connection, principal, game_id)


@router.delete("/games/{game_id}/wishlist")
def remove_from_wishlist(game_id: int, principal: Principal = CURRENT_PRINCIPAL) -> dict:
    with closing(get_connection()) as connection:
        _require_game(connection, game_id)
        connection.execute(
            "DELETE FROM user_wishlist_games WHERE username = ? AND game_id = ?",
            (principal.username, game_id),
        )
        return _changed(connection, principal, game_id)


@router.put("/games/{game_id}/favorite")
def add_to_favorites(
    game_id: int, principal: Annotated[Principal, Depends(get_current_principal)]
) -> dict:
    with closing(get_connection()) as connection:
        _require_game(connection, game_id)
        if not _list_state(connection, principal.username, game_id)["favorite"]:
            count, last_position = connection.execute(
                "SELECT COUNT(*), COALESCE(MAX(position), -1) FROM user_favorite_games WHERE username = ?",
                (principal.username,),
            ).fetchone()
            if count >= FAVORITE_GAMES_MAX:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"You can pick up to {FAVORITE_GAMES_MAX} favorite games.",
                )
            connection.execute(
                "INSERT INTO user_favorite_games (username, game_id, position) VALUES (?, ?, ?)",
                (principal.username, game_id, last_position + 1),
            )
        return _changed(connection, principal, game_id)


@router.delete("/games/{game_id}/favorite")
def remove_from_favorites(
    game_id: int, principal: Annotated[Principal, Depends(get_current_principal)]
) -> dict:
    with closing(get_connection()) as connection:
        _require_game(connection, game_id)
        connection.execute(
            "DELETE FROM user_favorite_games WHERE username = ? AND game_id = ?",
            (principal.username, game_id),
        )
        return _changed(connection, principal, game_id)
