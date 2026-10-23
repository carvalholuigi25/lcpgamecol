"""Bring games from the IGDB releases page into the library.

Release results are IGDB records, not library rows, so wishlisting, favoriting, or
editing one first imports it. The game data is always fetched from IGDB here, never
taken from the client. igdb_games remembers which library game each IGDB game
became, so importing the same release again returns the existing game.
"""

import os
from contextlib import closing
from datetime import UTC, datetime
from datetime import datetime as ndt

import httpx2 as httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status

from backend.auth.auth import Principal, get_current_principal
from backend.database.database import get_connection
from backend.realtime.hub import hub
from routes.games.lists import _list_state
from routes.games.routes import (
    _fetch_igdb_token,
    _igdb_company_names,
    _igdb_cover_url,
    _igdb_esrb_rating,
    _igdb_screenshot_url,
    _igdb_screenshots,
    _igdb_trailer_url,
    _igdb_website_url,
    insert_game,
)
from routes.games.schemas import GameCreate

router = APIRouter(tags=["games"])

IGDB_GAME_FIELDS = (
    "name,first_release_date,summary,game_modes.name,cover.url,screenshots.url,"
    "websites.category,websites.url,videos.video_id,involved_companies.developer,"
    "involved_companies.publisher,involved_companies.company.name,age_ratings.category,"
    "age_ratings.rating,genres.name,platforms.name,rating,aggregated_rating"
)
IgdbId = Path(ge=1, le=2**53)


def _fetch_igdb_game(igdb_id: int) -> dict:
    client_id = os.getenv("IGDB_CLIENT_ID")
    client_secret = os.getenv("IGDB_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(status_code=503, detail="IGDB credentials are not configured")

    try:
        with httpx.Client(timeout=10.0) as client:
            token = _fetch_igdb_token(client, client_id, client_secret)
            response = client.post(
                "https://api.igdb.com/v4/games",
                headers={"Client-ID": client_id, "Authorization": f"Bearer {token}"},
                content=f"fields {IGDB_GAME_FIELDS}; where id = {igdb_id}; limit 1;",
            )
            response.raise_for_status()
            games = response.json()
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
        raise HTTPException(status_code=502, detail="Unable to fetch the game from IGDB") from error
    if not games:
        raise HTTPException(status_code=404, detail="That game was not found on IGDB")
    return games[0]


def game_create_from_igdb(game: dict) -> GameCreate:
    released = game.get("first_release_date")
    if released is None:
        raise HTTPException(
            status_code=422,
            detail="This release has no release date yet, so it cannot be added to the library.",
        )
    release_date = ndt.fromtimestamp(released, tz=UTC)
    return GameCreate(
        title=game.get("name") or "Untitled game",
        genre=", ".join(genre["name"] for genre in game.get("genres") or []),
        release_year=release_date.year,
        release_date=release_date.date().isoformat(),
        description=game.get("summary") or "",
        gamemodes=", ".join(mode["name"] for mode in game.get("game_modes") or []) or "all",
        cover_image_url=_igdb_cover_url(game.get("cover")),
        image_url=_igdb_cover_url(game.get("cover")),
        screenshot_url=_igdb_screenshot_url((game.get("screenshots") or [None])[0]),
        developer_name=_igdb_company_names(game, "developer"),
        publisher_name=_igdb_company_names(game, "publisher"),
        website_url=_igdb_website_url(game),
        trailer_url=_igdb_trailer_url(game),
        screenshots=_igdb_screenshots(game),
        platforms=", ".join(platform["name"] for platform in game.get("platforms") or []) or "PC",
        user_rating=game.get("rating") or 0,
        critic_rating=game.get("aggregated_rating") or 0,
        esrb=_igdb_esrb_rating(game.get("age_ratings")),
    )


def _library_game_id(connection, igdb_id: int) -> int | None:
    row = connection.execute("SELECT game_id FROM igdb_games WHERE igdb_id = ?", (igdb_id,)).fetchone()
    return row["game_id"] if row else None


def _status(connection, principal: Principal, igdb_id: int) -> dict:
    game_id = _library_game_id(connection, igdb_id)
    lists = (
        _list_state(connection, principal.username, game_id)
        if game_id is not None
        else {"wishlisted": False, "favorite": False}
    )
    return {
        "igdb_id": igdb_id,
        "game_id": game_id,
        "wishlisted": lists["wishlisted"],
        "favorite": lists["favorite"],
    }


# Registered before /games/igdb/{igdb_id} so "links" is not read as an id.
@router.get("/games/igdb/links")
def get_igdb_links(
    ids: str = Query(pattern=r"^\d{1,16}(,\d{1,16}){0,99}$", description="Up to 100 comma-separated IGDB ids"),
    _principal: Principal = Depends(get_current_principal),
) -> dict[str, int]:
    """Map the given IGDB ids to their library game ids; ids not in the library are left out."""
    igdb_ids = list(dict.fromkeys(int(value) for value in ids.split(",")))
    placeholders = ", ".join("?" for _ in igdb_ids)
    with closing(get_connection()) as connection:
        rows = connection.execute(
            f"SELECT igdb_id, game_id FROM igdb_games WHERE igdb_id IN ({placeholders})", igdb_ids
        ).fetchall()
    return {str(row["igdb_id"]): row["game_id"] for row in rows}


@router.get("/games/igdb/{igdb_id}")
def get_igdb_game_status(
    igdb_id: int = IgdbId, principal: Principal = Depends(get_current_principal)
) -> dict:
    """Say whether an IGDB release is in the library and on the user's lists."""
    with closing(get_connection()) as connection:
        return _status(connection, principal, igdb_id)


@router.post("/games/igdb/{igdb_id}/import")
def import_igdb_game(
    response: Response,
    igdb_id: int = IgdbId,
    principal: Principal = Depends(get_current_principal),
) -> dict:
    """Add an IGDB release to the library, or return the copy imported earlier."""
    with closing(get_connection()) as connection:
        if _library_game_id(connection, igdb_id) is not None:
            return _status(connection, principal, igdb_id)

    game = game_create_from_igdb(_fetch_igdb_game(igdb_id))
    with closing(get_connection()) as connection:
        connection.execute("BEGIN IMMEDIATE")
        # Someone may have imported it while IGDB was answering.
        if _library_game_id(connection, igdb_id) is not None:
            connection.commit()
            return _status(connection, principal, igdb_id)
        game_id = insert_game(connection, game)
        connection.execute(
            "INSERT INTO igdb_games (igdb_id, game_id, imported_by, imported_at) VALUES (?, ?, ?, ?)",
            (igdb_id, game_id, principal.username, datetime.now(UTC).isoformat(timespec="seconds")),
        )
        connection.commit()
        result = _status(connection, principal, igdb_id)
    hub.publish("gameChanged", {"action": "created", "game_id": game_id, "title": game.title})
    response.status_code = status.HTTP_201_CREATED
    return result
