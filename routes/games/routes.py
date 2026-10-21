import json
import os
import time
from contextlib import closing
from datetime import UTC
from datetime import datetime as ndt

import httpx2 as httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from backend.auth.auth import require_admin
from backend.database.database import get_autoincrement, get_connection, reset_autoincrement
from routes.games.schemas import (
    IGDB_AGE_RATING_BY_ID,
    Game,
    GameCreate,
    GamePage,
    GamePlatform,
    GamePlatformVersions,
    GameReleasePage,
    GamesESRB,
    ModelGamesESRB,
    ModelGamesGameModes,
)

router = APIRouter()

current_datetime = ndt.now(tz=UTC)

def _igdb_cover_url(cover: dict | None) -> str:
    if not cover or not cover.get("url"):
        return ""
    return cover["url"].replace("//", "https://", 1).replace("t_thumb", "t_cover_big", 1)

def _igdb_screenshot_url(screenshot: dict | None) -> str:
    if not screenshot or not screenshot.get("url"):
        return ""
    return screenshot["url"].replace("//", "https://", 1).replace("t_thumb", "t_screenshot_med_2x", 1)


def _igdb_company_names(game: dict, role: str) -> str:
    return ", ".join(
        company["company"]["name"]
        for company in game.get("involved_companies") or []
        if company.get(role) and company.get("company", {}).get("name")
    )


def _igdb_website_url(game: dict) -> str:
    websites = game.get("websites") or []
    website = next(
        (entry for entry in websites if entry.get("category") == 1 and entry.get("url")),
        next((entry for entry in websites if entry.get("url")), None),
    )
    if not website:
        return ""
    url = website["url"]
    return url.replace("//", "https://", 1) if url.startswith("//") else url


def _igdb_trailer_url(game: dict) -> str:
    videos = game.get("videos") or []
    video_id = videos[0].get("video_id") if videos else None
    return f"https://www.youtube.com/watch?v={video_id}" if video_id else ""


def _igdb_screenshots(game: dict) -> list[str]:
    return [
        url
        for screenshot in game.get("screenshots", [])
        if (url := _igdb_screenshot_url(screenshot))
    ]


def _igdb_esrb_rating(age_ratings: list[dict] | None) -> GamesESRB | None:
    if not age_ratings:
        return None
    for age_rating in age_ratings:
        if age_rating.get("category") != 1:
            continue
        rating = IGDB_AGE_RATING_BY_ID.get(age_rating.get("rating"))
        if rating is not None:
            return rating
    return None


def _fetch_igdb_token(client: httpx.Client, client_id: str, client_secret: str) -> str:
    response = client.post(
        "https://id.twitch.tv/oauth2/token",
        params={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        },
    )
    response.raise_for_status()
    return response.json()["access_token"]


def _fetch_ext_covers_games(game_ids: list[int], limit: int = 10) -> list[dict]:
    """Fetch cover records for IGDB game IDs."""
    if not game_ids:
        return []
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="Cover limit must be between 1 and 500")

    client_id = os.environ.get("IGDB_CLIENT_ID") or os.getenv("IGDB_CLIENT_ID")
    client_secret = os.environ.get("IGDB_CLIENT_SECRET") or os.getenv("IGDB_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=503,
            detail="IGDB credentials are not configured",
        )

    ids = ",".join(str(game_id) for game_id in game_ids)
    query = (
        "fields alpha_channel,animated,checksum,game,game_localization,height,"
        "image_id,image_type,url,width; "
        f"where game = ({ids}); "
        f"limit {limit};"
    )
    try:
        with httpx.Client(timeout=10.0) as client:
            token = _fetch_igdb_token(client, client_id, client_secret)
            response = client.post(
                "https://api.igdb.com/v4/covers",
                headers={
                    "Client-ID": client_id,
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
                content=query,
            )
            response.raise_for_status()
            covers = response.json()
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch game covers from IGDB",
        ) from error

    for cover in covers:
        if cover.get("url"):
            cover["url"] = cover["url"].replace("//", "https://", 1)
    return covers

def _fetch_ext_artworks_games(game_ids: list[int], limit: int = 10) -> list[dict]:
    """Fetch artwork records for IGDB game IDs."""
    if not game_ids:
        return []
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="artwork limit must be between 1 and 500")

    client_id = os.environ.get("IGDB_CLIENT_ID") or os.getenv("IGDB_CLIENT_ID")
    client_secret = os.environ.get("IGDB_CLIENT_SECRET") or os.getenv("IGDB_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=503,
            detail="IGDB credentials are not configured",
        )

    ids = ",".join(str(game_id) for game_id in game_ids)
    query = (
        "fields alpha_channel,animated,checksum,game,height,"
        "image_id,image_type,url,width; "
        f"where game = ({ids}); "
        f"limit {limit};"
    )
    try:
        with httpx.Client(timeout=10.0) as client:
            token = _fetch_igdb_token(client, client_id, client_secret)
            response = client.post(
                "https://api.igdb.com/v4/artworks",
                headers={
                    "Client-ID": client_id,
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
                content=query,
            )
            response.raise_for_status()
            artworks = response.json()
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch game artworks from IGDB",
        ) from error

    for artwork in artworks:
        if artwork.get("url"):
            artwork["url"] = artwork["url"].replace("//", "https://", 1)
    return artworks


def _fetch_all_games_by_title(title: str, limit: int) -> list[Game]:
    # Docs: https://api-docs.igdb.com/#getting-started
    title = title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="A game title is required")

    client_id = os.environ.get("IGDB_CLIENT_ID") or os.getenv("IGDB_CLIENT_ID")
    client_secret = os.environ.get("IGDB_CLIENT_SECRET") or os.getenv("IGDB_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=503,
            detail="IGDB credentials are not configured",
        )

    igdb_title = json.dumps(title)
    query = (
        "fields name,first_release_date,summary,game_modes.id,game_modes.name,cover.url,screenshots.url,websites.category,websites.url,videos.video_id,"
        "involved_companies.developer,involved_companies.publisher,involved_companies.company.name,age_ratings.category,age_ratings.rating,genres.name,"
        "platforms.name,rating,aggregated_rating; "
        f"where name ~ {igdb_title}; "
        "sort first_release_date asc; "
        f"limit {limit};"
    )
    try:
        with httpx.Client(timeout=10.0) as client:
            token = _fetch_igdb_token(client, client_id, client_secret)
            response = client.post(
                "https://api.igdb.com/v4/games",
                headers={
                    "Client-ID": client_id,
                    "Authorization": f"Bearer {token}",
                },
                content=query,
            )
            response.raise_for_status()
            games = response.json()
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch all releases by title from IGDB",
        ) from error

    return [
        Game(
            id=game["id"],
            title=game.get("name", "Untitled game"),
            genre=", ".join(genre["name"] for genre in game.get("genres", [])),
            release_year=ndt.fromtimestamp(
                game["first_release_date"], tz=UTC
            ).year,
            release_date=ndt.fromtimestamp(
                game["first_release_date"], tz=UTC
            ).date().isoformat(),
            description=game.get("summary", ""),
            gamemodes=", ".join(mode["name"] for mode in game.get("game_modes", [])),
            cover_image_url=_igdb_cover_url(game.get("cover")),
            image_url=_igdb_cover_url(game.get("cover")),
            screenshot_url=_igdb_screenshot_url((game.get("screenshots") or [None])[0]),
            developer_name=_igdb_company_names(game, "developer"),
            publisher_name=_igdb_company_names(game, "publisher"),
            website_url=_igdb_website_url(game),
            trailer_url=_igdb_trailer_url(game),
            screenshots=_igdb_screenshots(game),
            platforms=", ".join(
                platform["name"] for platform in game.get("platforms", [])
            ),
            user_rating=game.get("rating", 0),
            critic_rating=game.get("aggregated_rating", 0),
            esrb=_igdb_esrb_rating(game.get("age_ratings")),
        )
        for game in games
    ]

def _fetch_all_platforms(limit: int) -> list[GamePlatform]:
    # Docs: https://api-docs.igdb.com/#getting-started
    client_id = os.environ.get("IGDB_CLIENT_ID") or os.getenv("IGDB_CLIENT_ID")
    client_secret = os.environ.get("IGDB_CLIENT_SECRET") or os.getenv("IGDB_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=503,
            detail="IGDB credentials are not configured",
        )

    query = (
        "fields alternative_name,category,checksum,created_at,generation,name,"
        "platform_family,platform_logo,platform_type,slug,summary,updated_at,url; "
        f"limit {limit};"
    )
    try:
        with httpx.Client(timeout=10.0) as client:
            token = _fetch_igdb_token(client, client_id, client_secret)
            response = client.post(
                "https://api.igdb.com/v4/platforms",
                headers={
                    "Client-ID": client_id,
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "text/plain",
                },
                content=query,
            )
            response.raise_for_status()
            platforms = response.json()
            if not isinstance(platforms, list):
                raise TypeError("IGDB platforms response must be a list")
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch all platforms from IGDB",
        ) from error

    return [
        GamePlatform(
            alternative_name=platform.get("alternative_name") or "",
            checksum=platform.get("checksum") or "",
            created_at=ndt.fromtimestamp(
                platform.get("created_at") or 0, tz=UTC
            ).date().isoformat(),
            generation=platform.get("generation") or 0,
            name=platform.get("name") or "",
            platform_family=platform.get("platform_family") or 0,
            platform_logo=platform.get("platform_logo") or 0,
            platform_type=platform.get("platform_type") or 0,
            slug=platform.get("slug") or "",
            summary=platform.get("summary") or "",
            updated_at=ndt.fromtimestamp(
                platform.get("updated_at") or 0, tz=UTC
            ).date().isoformat(),
            url=platform.get("url") or "",
        )
        for platform in platforms
    ]

def _fetch_all_platforms_versions(limit: int) -> list[GamePlatformVersions]:
    # Docs: https://api-docs.igdb.com/#getting-started
    client_id = os.environ.get("IGDB_CLIENT_ID") or os.getenv("IGDB_CLIENT_ID")
    client_secret = os.environ.get("IGDB_CLIENT_SECRET") or os.getenv("IGDB_CLIENT_SECRET")

    if limit <= 0:
        raise HTTPException(
            status_code=404,
            detail="Please provide the limit of data (min: 1)",
        )

    if not client_id or not client_secret:
        raise HTTPException(
            status_code=503,
            detail="IGDB credentials are not configured",
        )

    query = (
        "fields checksum,connectivity,cpu,graphics,main_manufacturer,media,memory,name,os,output,"
        "companies.checksum,companies.comment,companies.company,companies.developer,companies.manufacturer,"
        "platform_logo.alpha_channel,platform_logo.animated,platform_logo.checksum,"
        "platform_logo.height,platform_logo.image_id,platform_logo.url,platform_logo.width,"
        "platform_version_release_dates.checksum,platform_version_release_dates.created_at,"
        "platform_version_release_dates.date,platform_version_release_dates.date_format,"
        "platform_version_release_dates.human,platform_version_release_dates.m,"
        "platform_version_release_dates.platform_version,platform_version_release_dates.release_region,"
        "platform_version_release_dates.updated_at,platform_version_release_dates.y,"
        "resolutions,slug,sound,storage,summary,url;"
        f"limit {limit};"
    )
    try:
        with httpx.Client(timeout=10.0) as client:
            token = _fetch_igdb_token(client, client_id, client_secret)
            response = client.post(
                "https://api.igdb.com/v4/platform_versions",
                headers={
                    "Client-ID": client_id,
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "text/plain",
                },
                content=query,
            )
            response.raise_for_status()
            platformsv = response.json()
            if not isinstance(platformsv, list):
                raise TypeError("IGDB platforms versions response must be a list")
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch all platform versions from IGDB",
        ) from error

    return [
        GamePlatformVersions(
            checksum=platformv["checksum"] or platformv.get("checksum") or "",
            companies=platformv.get("companies") or [],
            connectivity=platformv.get("connectivity") or "",
            cpu=platformv.get("cpu") or "",
            graphics=platformv.get("graphics") or "",
            main_manufacturer=int(platformv.get("main_manufacturer") or 1),
            media=platformv.get("media") or "",
            memory=platformv.get("memory") or "",
            name=platformv.get("name") or "",
            os=platformv.get("os") or "",
            output=platformv.get("output") or "",
            platform_logo=platformv.get("platform_logo"),
            platform_version_release_dates=platformv.get("platform_version_release_dates"),
            slug=platformv.get("slug") or "",
            summary=platformv.get("summary") or "",
            url=platformv["url"] or platformv.get("url") or "",
        )
        for platformv in platformsv
    ]

def _fetch_all_esrb_ratings(limit: int) -> list[ModelGamesESRB]:
    # Docs: https://api-docs.igdb.com/#getting-started
    client_id = os.environ.get("IGDB_CLIENT_ID") or os.getenv("IGDB_CLIENT_ID")
    client_secret = os.environ.get("IGDB_CLIENT_SECRET") or os.getenv("IGDB_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=503,
            detail="IGDB credentials are not configured",
        )

    query = (
        "fields organization,rating; "
        f"limit {limit};"
    )
    try:
        with httpx.Client(timeout=10.0) as client:
            token = _fetch_igdb_token(client, client_id, client_secret)
            response = client.post(
                "https://api.igdb.com/v4/age_rating_categories",
                headers={
                    "Client-ID": client_id,
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "text/plain",
                },
                content=query,
            )
            response.raise_for_status()
            esrb_ratings = response.json()
            if not isinstance(esrb_ratings, list):
                raise TypeError("IGDB age ratings response must be a list")
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch all ESRB ratings from IGDB",
        ) from error

    return [
        ModelGamesESRB(
            organization=rating.get("organization", "") or "",
            rating=rating.get("rating", "") or "",
        )
        for rating in esrb_ratings
    ]

def _fetch_all_games_by_date(
    year: int, month: int, day: int, limit: int, skip: int
) -> GameReleasePage:
    # Docs: https://api-docs.igdb.com/#getting-started
    client_id = os.environ.get("IGDB_CLIENT_ID") or os.getenv("IGDB_CLIENT_ID")
    client_secret = os.environ.get("IGDB_CLIENT_SECRET") or os.getenv("IGDB_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=503,
            detail="IGDB credentials are not configured",
        )


    tzinfo = UTC
    parsed_date = int(ndt(year, month, day, 0, 0, 0, tzinfo=tzinfo).timestamp())
    where_clause = f"where first_release_date >= {parsed_date}; "
    query = (
        "fields name,first_release_date,summary,game_modes.id,game_modes.name,cover.url,screenshots.url,websites.category,websites.url,videos.video_id,"
        "involved_companies.developer,involved_companies.publisher,involved_companies.company.name,age_ratings.category,age_ratings.rating,genres.name,"
        f"platforms.name,rating,aggregated_rating; {where_clause}"
        "sort first_release_date asc; "
        f"offset {skip}; "
        f"limit {limit};"
    )
    try:
        with httpx.Client(timeout=10.0) as client:
            token = _fetch_igdb_token(client, client_id, client_secret)
            headers = {
                "Client-ID": client_id,
                "Authorization": f"Bearer {token}",
            }
            response = client.post(
                "https://api.igdb.com/v4/games",
                headers=headers,
                content=query,
            )
            response.raise_for_status()
            games = response.json()
            count_response = client.post(
                "https://api.igdb.com/v4/games/count",
                headers=headers,
                content=where_clause,
            )
            count_response.raise_for_status()
            total = count_response.json().get("count", 0)
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch all releases from IGDB",
        ) from error

    items = [
        Game(
            id=game["id"],
            title=game.get("name", "Untitled game"),
            genre=", ".join(genre["name"] for genre in game.get("genres", [])),
            release_year=ndt.fromtimestamp(
                game["first_release_date"], tz=UTC
            ).year,
            release_date=ndt.fromtimestamp(
                game["first_release_date"], tz=UTC
            ).date().isoformat(),
            description=game.get("summary", ""),
            gamemodes=[ModelGamesGameModes(**mode) for mode in game.get("game_modes", [])],
            cover_image_url=_igdb_cover_url(game.get("cover")),
            image_url=_igdb_cover_url(game.get("cover")),
            screenshot_url=_igdb_screenshot_url((game.get("screenshots") or [None])[0]),
            developer_name=_igdb_company_names(game, "developer"),
            publisher_name=_igdb_company_names(game, "publisher"),
            website_url=_igdb_website_url(game),
            trailer_url=_igdb_trailer_url(game),
            screenshots=_igdb_screenshots(game),
            platforms=", ".join(
                platform["name"] for platform in game.get("platforms", [])
            ),
            user_rating=game.get("rating", 0),
            critic_rating=game.get("aggregated_rating", 0),
            esrb=_igdb_esrb_rating(game.get("age_ratings")),
        )
        for game in games
    ]
    return GameReleasePage(items=items, total=total, page_size=limit)


def _fetch_next_releases(limit: int) -> list[Game]:
    # Docs: https://api-docs.igdb.com/#getting-started
    client_id = os.environ.get("IGDB_CLIENT_ID") or os.getenv("IGDB_CLIENT_ID")
    client_secret = os.environ.get("IGDB_CLIENT_SECRET") or os.getenv("IGDB_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=503,
            detail="IGDB credentials are not configured",
        )

    release_timestamp = int(time.time())
    query = (
        "fields name,first_release_date,summary,cover.url,screenshots.url,websites.category,websites.url,videos.video_id,"
        "involved_companies.developer,involved_companies.publisher,involved_companies.company.name,age_ratings.category,age_ratings.rating,genres.name,"
        "platforms.name,rating,aggregated_rating; "
        f"where first_release_date > {release_timestamp}; "
        "sort first_release_date asc; "
        f"limit {limit};"
    )
    try:
        with httpx.Client(timeout=10.0) as client:
            token = _fetch_igdb_token(client, client_id, client_secret)
            response = client.post(
                "https://api.igdb.com/v4/games",
                headers={
                    "Client-ID": client_id,
                    "Authorization": f"Bearer {token}",
                },
                content=query,
            )
            response.raise_for_status()
            games = response.json()
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch next releases from IGDB",
        ) from error

    return [
        Game(
            id=game["id"],
            title=game.get("name", "Untitled game"),
            genre=", ".join(genre["name"] for genre in game.get("genres", [])),
            release_year=ndt.fromtimestamp(
                game["first_release_date"], tz=UTC
            ).year,
            release_date=ndt.fromtimestamp(
                game["first_release_date"], tz=UTC
            ).date().isoformat(),
            description=game.get("summary", ""),
            cover_image_url=_igdb_cover_url(game.get("cover")),
            image_url=_igdb_cover_url(game.get("cover")),
            screenshot_url=_igdb_screenshot_url((game.get("screenshots") or [None])[0]),
            developer_name=_igdb_company_names(game, "developer"),
            publisher_name=_igdb_company_names(game, "publisher"),
            website_url=_igdb_website_url(game),
            trailer_url=_igdb_trailer_url(game),
            screenshots=_igdb_screenshots(game),
            platforms=", ".join(
                platform["name"] for platform in game.get("platforms", [])
            ),
            user_rating=game.get("rating", 0),
            critic_rating=game.get("aggregated_rating", 0),
            esrb=_igdb_esrb_rating(game.get("age_ratings")),
        )
        for game in games
    ]

def game_from_row(row) -> Game:
    game = dict(row)
    game["screenshots"] = json.loads(game.get("screenshots") or "[]")
    return Game(**game)


def game_database_values(game: GameCreate) -> tuple:
    values = game.model_dump()
    values["screenshots"] = json.dumps(values["screenshots"])
    return tuple(values.values())

@router.post(
    "/games",
    response_model=Game,
    status_code=201,
    tags=["games"],
    dependencies=[Depends(require_admin)],
)
def create_game(game: GameCreate) -> Game:
    values = game_database_values(game)
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            """
            INSERT INTO games (title, genre, release_year, release_date, description, cover_image_url, image_url, screenshot_url, developer_name, publisher_name, website_url, trailer_url, screenshots, platforms, gamemodes, editions, user_rating, critic_rating, wishlisted, hoursplayed, esrb, minimum_system_requirements, recommended_system_requirements)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        connection.commit()
        game_id = cursor.lastrowid
    return Game(id=game_id, **game.model_dump())


@router.get("/games", response_model=list[Game], tags=["games"])
def list_games(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
) -> list[Game]:
    with closing(get_connection()) as connection:
        rows = connection.execute(
            "SELECT * FROM games ORDER BY id LIMIT ? OFFSET ?", (limit, skip)
        ).fetchall()
    return [game_from_row(row) for row in rows]


@router.get("/games/page", response_model=GamePage, tags=["games"])
def list_games_page(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
) -> GamePage:
    with closing(get_connection()) as connection:
        total = connection.execute("SELECT COUNT(*) FROM games").fetchone()[0]
        rows = connection.execute(
            "SELECT * FROM games ORDER BY id LIMIT ? OFFSET ?", (limit, skip)
        ).fetchall()
    return GamePage(
        items=[game_from_row(row) for row in rows],
        total=total,
        page_size=limit,
    )


@router.get("/games/all-releases", response_model=GameReleasePage, tags=["games"])
def list_all_releases(
    year: int = current_datetime.year,
    month: int = current_datetime.month,
    day: int = current_datetime.day,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
) -> list[Game]:
    return _fetch_all_games_by_date(year, month, day, limit, skip)

@router.get("/games/title", response_model=list[Game], tags=["games"])
def list_all_releases_by_title(
    title: str = "", 
    limit: int = Query(10, ge=1, le=100)
) -> list[Game]:
    return _fetch_all_games_by_title(title, limit)

@router.post("/games/covers", response_model=list[dict], tags=["games"])
def list_all_covers(
    gamesids: list[int], 
    limit: int = Query(10, ge=1, le=100)
) -> list[dict]:
    return _fetch_ext_covers_games(gamesids, limit)

@router.post("/games/artworks", response_model=list[dict], tags=["games"])
def list_all_artworks(
    gamesids: list[int], 
    limit: int = Query(10, ge=1, le=100)
) -> list[dict]:
    return _fetch_ext_artworks_games(gamesids, limit)

@router.get("/games/next-releases", response_model=list[Game], tags=["games"])
def list_next_releases(
    limit: int = Query(10, ge=1, le=100),
) -> list[Game]:
    return _fetch_next_releases(limit)

@router.get("/games/esrb-ratings", response_model=list[ModelGamesESRB], tags=["games"])
def list_esrb_ratings(
    limit: int = Query(100, ge=1, le=100),
) -> list[ModelGamesESRB]:
    return _fetch_all_esrb_ratings(limit)


@router.get("/games/search", response_model=list[Game], tags=["games"])
def search_games(
    title: str | None = None,
    genre: str | None = None,
    platforms: str | None = None,
    release_year: int | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
) -> list[Game]:
    filters = []
    parameters: list[str | int] = []
    for column, value in (("title", title), ("genre", genre), ("platforms", platforms)):
        if value:
            filters.append(f"{column} LIKE ?")
            parameters.append(f"%{value}%")
    if release_year is not None:
        filters.append("release_year = ?")
        parameters.append(release_year)

    query = "SELECT * FROM games"
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY id LIMIT ? OFFSET ?"
    parameters.extend((limit, skip))

    with closing(get_connection()) as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [game_from_row(row) for row in rows]


@router.get("/games/external-search", response_model=list[Game], tags=["games"])
def search_external_games(
    query: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(10, ge=1, le=100),
) -> list[Game]:
    return _fetch_all_games_by_title(query, limit)

@router.get("/games/platforms", response_model=list[GamePlatform], tags=["games"])
def fetch_platforms_games(
    limit: int = Query(10, ge=1, le=100),
) -> list[GamePlatform]:
    return _fetch_all_platforms(limit)

@router.get("/games/platforms/versions", response_model=list[GamePlatformVersions], tags=["games"])
def fetch_platforms_versions_games(
    limit: int = Query(1, ge=1, le=100)
) -> list[GamePlatformVersions]:
    return _fetch_all_platforms_versions(limit)

@router.get(
    "/games/get-autoincrement",
    response_model=dict[str, int | str],
    tags=["games"],
    dependencies=[Depends(require_admin)],
)
def fetch_games_autoincrement() -> dict[str, int | str]:
    return {
        "table": "games",
        "next_id": get_autoincrement("games"),
    }

@router.post(
    "/games/reset-autoincrement",
    response_model=dict[str, int | str],
    tags=["games"],
    dependencies=[Depends(require_admin)],
)
def reset_games_autoincrement() -> dict[str, int | str]:
    return {
        "table": "games",
        "next_id": reset_autoincrement("games"),
    }

@router.get("/games/{game_id}", response_model=Game, tags=["games"])
def get_game(game_id: int) -> Game:
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT * FROM games WHERE id = ?", (game_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return game_from_row(row)


@router.put(
    "/games/{game_id}",
    response_model=Game,
    tags=["games"],
    dependencies=[Depends(require_admin)],
)
def update_game(game_id: int, game: GameCreate) -> Game:
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            """
            UPDATE games
            SET title = ?, genre = ?, release_year = ?, release_date = ?,
                description = ?, cover_image_url = ?, image_url = ?, screenshot_url = ?,
                developer_name = ?, publisher_name = ?, website_url = ?, trailer_url = ?, screenshots = ?,
                platforms = ?, gamemodes = ?, editions = ?, user_rating = ?, critic_rating = ?,
                wishlisted = ?, hoursplayed = ?, esrb = ?,
                minimum_system_requirements = ?, recommended_system_requirements = ?
            WHERE id = ?
            """,
            (*game_database_values(game), game_id),
        )
        connection.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Game not found")
    return Game(id=game_id, **game.model_dump())


@router.delete(
    "/games/all",
    status_code=204,
    tags=["games"],
    dependencies=[Depends(require_admin)],
)
def delete_all_games() -> None:
    with closing(get_connection()) as connection:
        cursor = connection.execute("DELETE FROM games")
        connection.commit()
        reset_autoincrement("games")
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="No games found to delete")


@router.delete(
    "/games/{game_id}",
    status_code=204,
    tags=["games"],
    dependencies=[Depends(require_admin)],
)
def delete_game(game_id: int) -> None:
    with closing(get_connection()) as connection:
        cursor = connection.execute("DELETE FROM games WHERE id = ?", (game_id,))
        connection.commit()
        reset_autoincrement("games")
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Game not found")