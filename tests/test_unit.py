import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx2 as httpx
import jwt
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import main
import schemas.schemas as shared_schemas
from backend.auth import auth, rate_limit
from backend.database import database
from routes.achievements.schemas import (
    Achievement,
    AchievementCreate,
    AchievementStatus,
    AchievementType,
)
from routes.games import routes as games_routes
from routes.games.routes import _igdb_cover_url, _igdb_screenshot_url
from routes.games.schemas import (
    Game,
    GameCreate,
    GameEdition,
    GameModes,
    Gameplatforms,
    GamesESRB,
)


def make_token(**claims) -> str:
    claims.setdefault("exp", datetime.now(UTC) + timedelta(minutes=5))
    return jwt.encode(claims, auth.JWT_SECRET, algorithm=auth.JWT_ALGORITHM)


def assert_unauthorized(func, *args, detail=None):
    with pytest.raises(HTTPException) as exc_info:
        func(*args)
    assert exc_info.value.status_code == 401
    assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}
    if detail is not None:
        assert exc_info.value.detail == detail


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test.db")
    database.initialize_database()
    return tmp_path / "test.db"


def test_database_path_is_next_to_database_module():
    assert database.DATABASE_PATH == Path(database.__file__).parent / "mydb.db"


def test_auth_and_database_live_in_backend_package():
    project_root = Path(main.__file__).parent

    assert Path(auth.__file__).parent == project_root / "backend" / "auth"
    assert Path(rate_limit.__file__).parent == project_root / "backend" / "auth"
    assert Path(database.__file__).parent == project_root / "backend" / "database"
    assert not (project_root / "auth").exists()
    assert not (project_root / "database").exists()


# --- auth: user configuration -------------------------------------------------


def test_load_users_falls_back_to_single_admin(monkeypatch):
    monkeypatch.delenv("AUTH_USERS", raising=False)
    monkeypatch.setattr(auth, "AUTH_PASSWORD", "configured-password")

    assert auth._load_users() == {
        auth.AUTH_USERNAME: ("configured-password", auth.ROLE_ADMIN)
    }


def test_load_users_has_no_admin_without_a_password(monkeypatch):
    monkeypatch.delenv("AUTH_USERS", raising=False)
    monkeypatch.setattr(auth, "AUTH_PASSWORD", "")

    assert auth._load_users() == {}


def test_load_users_rejects_entries_without_a_password(monkeypatch):
    monkeypatch.setenv("AUTH_USERS", "alice::admin")

    with pytest.raises(ValueError, match="no password"):
        auth._load_users()


def test_load_users_parses_env_and_skips_blank_entries(monkeypatch):
    monkeypatch.setenv("AUTH_USERS", " alice:pw1:admin , ,bob:pw2:viewer,")

    assert auth._load_users() == {
        "alice": ("pw1", "admin"),
        "bob": ("pw2", "viewer"),
    }


@pytest.mark.parametrize(
    "raw", ["alice:pw:superuser", "alice:pw", "alice:pw:admin:extra"]
)
def test_load_users_rejects_malformed_entries(monkeypatch, raw):
    monkeypatch.setenv("AUTH_USERS", raw)

    with pytest.raises(ValueError):
        auth._load_users()


# --- auth: login -----------------------------------------------------------------


@pytest.fixture()
def users(monkeypatch):
    monkeypatch.setattr(
        auth,
        "AUTH_USERS",
        {"alice": ("secret", auth.ROLE_ADMIN), "bob": ("pw", auth.ROLE_VIEWER)},
    )


def test_authenticate_returns_principal_with_role(users):
    form = SimpleNamespace(username="bob", password="pw")

    assert auth.authenticate(form) == auth.Principal("bob", auth.ROLE_VIEWER)


@pytest.mark.parametrize(
    "username, password", [("alice", "wrong"), ("nobody", "secret"), ("alice", "")]
)
def test_authenticate_rejects_bad_credentials(users, username, password):
    form = SimpleNamespace(username=username, password=password)

    assert_unauthorized(auth.authenticate, form, detail="Incorrect username or password")


def test_get_role_for_username(users):
    assert auth.get_role_for_username("alice") == auth.ROLE_ADMIN
    assert_unauthorized(auth.get_role_for_username, "nobody", detail="Unknown user")


# --- auth: access tokens ---------------------------------------------------------


def test_access_token_round_trip():
    token = auth.create_access_token("alice", auth.ROLE_VIEWER)

    claims = jwt.decode(token, auth.JWT_SECRET, algorithms=[auth.JWT_ALGORITHM])
    assert claims["type"] == "access"
    assert claims["role"] == auth.ROLE_VIEWER
    assert auth.get_current_principal(token) == auth.Principal("alice", auth.ROLE_VIEWER)
    assert auth.get_current_user(token) == "alice"


def test_access_token_expires_after_configured_lifetime():
    before = datetime.now(UTC)
    token = auth.create_access_token("alice", auth.ROLE_ADMIN)

    exp = jwt.decode(token, auth.JWT_SECRET, algorithms=[auth.JWT_ALGORITHM])["exp"]
    expected = before.timestamp() + auth.TOKEN_EXPIRE_SECONDS
    assert expected - 1 <= exp <= expected + 2


@pytest.mark.parametrize(
    "token",
    [
        pytest.param("not-a-jwt", id="garbage"),
        pytest.param(
            make_token(sub="alice", role="admin", exp=datetime.now(UTC) - timedelta(seconds=1)),
            id="expired",
        ),
        pytest.param(
            jwt.encode(
                {"sub": "alice", "role": "admin", "exp": datetime.now(UTC) + timedelta(minutes=5)},
                "some-other-secret-that-is-long-enough",
                algorithm="HS256",
            ),
            id="wrong-secret",
        ),
        pytest.param(make_token(sub="alice"), id="missing-role"),
        pytest.param(make_token(role="admin"), id="missing-sub"),
        pytest.param(make_token(sub="alice", role="root"), id="unknown-role"),
        pytest.param(make_token(sub="alice", role="admin", type="refresh"), id="refresh-type"),
    ],
)
def test_access_token_rejected(token):
    assert_unauthorized(
        auth.get_current_principal, token, detail="Invalid or expired authentication token"
    )


def test_access_token_rejects_non_string_subject(monkeypatch):
    monkeypatch.setattr(
        auth.jwt, "decode", lambda *args, **kwargs: {"sub": 123, "role": "admin"}
    )

    assert_unauthorized(auth.get_current_user, "valid-token")


def test_access_token_without_type_claim_is_accepted():
    token = make_token(sub="alice", role=auth.ROLE_ADMIN)

    assert auth.get_current_user(token) == "alice"


def test_principal_falls_back_to_cookie():
    token = auth.create_access_token("alice", auth.ROLE_ADMIN)
    request = SimpleNamespace(cookies={auth.AUTH_COOKIE_NAME: token})

    assert auth.get_current_user(None, request) == "alice"


def test_bearer_token_takes_precedence_over_cookie():
    bearer = auth.create_access_token("alice", auth.ROLE_ADMIN)
    request = SimpleNamespace(cookies={auth.AUTH_COOKIE_NAME: "garbage"})

    assert auth.get_current_user(bearer, request) == "alice"


@pytest.mark.parametrize("request_obj", [None, SimpleNamespace(cookies={})])
def test_principal_requires_some_token(request_obj):
    assert_unauthorized(auth.get_current_principal, None, request_obj)


# --- auth: roles -----------------------------------------------------------------


def test_require_role_allows_listed_roles():
    dependency = auth.require_role(auth.ROLE_ADMIN, auth.ROLE_VIEWER)
    viewer = auth.Principal("bob", auth.ROLE_VIEWER)

    assert dependency(viewer) is viewer


def test_require_admin_forbids_viewer():
    with pytest.raises(HTTPException) as exc_info:
        auth.require_admin(auth.Principal("bob", auth.ROLE_VIEWER))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Insufficient permissions"


# --- auth: refresh tokens --------------------------------------------------------


def test_refresh_token_round_trip():
    token = auth.create_refresh_token("alice")

    claims = jwt.decode(token, auth.JWT_SECRET, algorithms=[auth.JWT_ALGORITHM])
    assert "role" not in claims
    assert auth.get_current_user_from_refresh_token(token) == "alice"


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(None, id="missing"),
        pytest.param("not-a-jwt", id="garbage"),
        pytest.param(make_token(sub="alice", type="access", role="admin"), id="access-type"),
        pytest.param(make_token(sub="alice"), id="missing-type"),
        pytest.param(
            make_token(sub="alice", type="refresh", exp=datetime.now(UTC) - timedelta(seconds=1)),
            id="expired",
        ),
    ],
)
def test_refresh_token_rejected(token):
    assert_unauthorized(
        auth.get_current_user_from_refresh_token, token, detail="Invalid refresh token"
    )


def test_access_token_cannot_be_used_as_refresh_token():
    token = auth.create_access_token("alice", auth.ROLE_ADMIN)

    assert_unauthorized(auth.get_current_user_from_refresh_token, token)


# --- database --------------------------------------------------------------------


def test_initialize_database_is_idempotent(temp_db):
    database.initialize_database()

    with closing(database.get_connection()) as connection:
        tables = {
            row["name"]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        game_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(games)")
        }
    assert {"games", "achievements"} <= tables
    assert {
        "developer_name",
        "publisher_name",
        "website_url",
        "trailer_url",
        "screenshots",
        "minimum_system_requirements",
        "recommended_system_requirements",
    } <= game_columns


def test_initialize_database_adds_requirements_to_existing_games(temp_db):
    with closing(database.get_connection()) as connection:
        connection.execute("DROP TABLE achievements")
        connection.execute("DROP TABLE games")
        connection.execute(
            "CREATE TABLE games (id INTEGER PRIMARY KEY, esrb TEXT NULL)"
        )
        connection.execute("INSERT INTO games (id, esrb) VALUES (1, 't')")
        connection.commit()

    database.initialize_database()

    with closing(database.get_connection()) as connection:
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(games)")
        }
        game = connection.execute("SELECT id, esrb FROM games WHERE id = 1").fetchone()
    assert {
        "developer_name",
        "publisher_name",
        "website_url",
        "trailer_url",
        "screenshots",
        "minimum_system_requirements",
        "recommended_system_requirements",
    } <= columns
    assert game["esrb"] == "t"


def test_get_connection_enables_foreign_keys_and_row_factory(temp_db):
    with closing(database.get_connection()) as connection:
        assert connection.row_factory is sqlite3.Row
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_seed_database_is_idempotent(temp_db):
    database.seed_database()
    database.seed_database()

    with closing(database.get_connection()) as connection:
        assert connection.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM achievements").fetchone()[0] == 4
        orphaned = connection.execute(
            "SELECT COUNT(*) FROM achievements WHERE game_id NOT IN (SELECT id FROM games)"
        ).fetchone()[0]
    assert orphaned == 0


def test_initialize_database_migrates_legacy_esrb_labels(temp_db):
    database.seed_database()
    with closing(database.get_connection()) as connection:
        connection.execute(
            "UPDATE games SET esrb = 'Everyone 10+' WHERE id = 1"
        )
        connection.commit()

    database.initialize_database()

    with closing(database.get_connection()) as connection:
        esrb = connection.execute(
            "SELECT esrb FROM games WHERE id = 1"
        ).fetchone()[0]
    assert esrb == str(GamesESRB.E10.value)


def test_initialize_database_preserves_valid_low_age_rating_ids(temp_db):
    database.seed_database()
    with closing(database.get_connection()) as connection:
        connection.execute("UPDATE games SET esrb = '1' WHERE id = 1")
        connection.commit()

    database.initialize_database()

    with closing(database.get_connection()) as connection:
        row = connection.execute("SELECT * FROM games WHERE id = 1").fetchone()
    assert row["esrb"] == "1"
    assert games_routes.game_from_row(row).esrb == GamesESRB.Three


def test_seed_database_stores_enum_values_as_plain_text(temp_db):
    database.seed_database()

    with closing(database.get_connection()) as connection:
        esrb_values = {row[0] for row in connection.execute("SELECT esrb FROM games")}
    assert esrb_values <= {str(rating.value) for rating in GamesESRB}


def test_deleting_game_cascades_to_achievements(temp_db):
    database.seed_database()

    with closing(database.get_connection()) as connection:
        game_id = connection.execute(
            "SELECT game_id FROM achievements GROUP BY game_id ORDER BY COUNT(*) DESC"
        ).fetchone()[0]
        connection.execute("DELETE FROM games WHERE id = ?", (game_id,))
        connection.commit()
        remaining = connection.execute(
            "SELECT COUNT(*) FROM achievements WHERE game_id = ?", (game_id,)
        ).fetchone()[0]
    assert remaining == 0


def test_achievement_requires_existing_game(temp_db):
    with closing(database.get_connection()) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO achievements (title, game_id) VALUES (?, ?)", ("Orphan", 999)
        )


@pytest.mark.parametrize("table", ["games", "achievements"])
def test_autoincrement_on_empty_table_is_one(temp_db, table):
    assert database.get_autoincrement(table) == 1
    assert database.reset_autoincrement(table) == 1


def test_get_autoincrement_returns_next_id(temp_db):
    database.seed_database()

    assert database.get_autoincrement("games") == 4
    assert database.get_autoincrement("achievements") == 5


def test_reset_autoincrement_reuses_ids_after_deletes(temp_db):
    database.seed_database()
    with closing(database.get_connection()) as connection:
        connection.execute("DELETE FROM games WHERE id = 3")
        connection.commit()

    assert database.reset_autoincrement("games") == 3

    with closing(database.get_connection()) as connection:
        cursor = connection.execute(
            "INSERT INTO games (title, genre, release_year, platforms) VALUES ('X', 'Y', 2020, 'PC')"
        )
        connection.commit()
    assert cursor.lastrowid == 3


@pytest.mark.parametrize(
    "func", [database.get_autoincrement, database.reset_autoincrement]
)
@pytest.mark.parametrize("table", ["users", "games; DROP TABLE games", ""])
def test_autoincrement_rejects_unsupported_tables(temp_db, func, table):
    with pytest.raises(ValueError, match="Unsupported autoincrement table"):
        func(table)


# --- rate limiting ---------------------------------------------------------------


@pytest.fixture()
def rate_limited_client(monkeypatch):
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_REQUESTS", 2)
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_WINDOW_SECONDS", 10)
    clock = SimpleNamespace(now=1000.0)
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: clock.now)

    app = FastAPI()
    app.add_middleware(rate_limit.RateLimitMiddleware)
    app.get("/")(lambda: {"ok": True})
    app.get("/assets/site.css")(lambda: {"ok": True})
    app.get("/assets/site.js")(lambda: {"ok": True})

    with TestClient(app) as client:
        yield client, clock


@pytest.mark.parametrize("asset_path", ["/assets/site.css", "/assets/site.js"])
def test_rate_limit_allows_css_and_js_when_limit_is_reached(
    rate_limited_client, asset_path
):
    client, _ = rate_limited_client
    client.get("/")
    client.get("/")

    assert client.get(asset_path).status_code == 200
    assert client.get("/").status_code == 429


def test_rate_limit_blocks_after_limit(rate_limited_client):
    client, clock = rate_limited_client

    assert client.get("/").status_code == 200
    clock.now += 4
    assert client.get("/").status_code == 200

    response = client.get("/")
    assert response.status_code == 429
    assert response.json() == {"detail": "Rate limit exceeded"}
    assert response.headers["Retry-After"] == "6"


def test_rate_limit_rejected_requests_do_not_extend_window(rate_limited_client):
    client, clock = rate_limited_client
    client.get("/")
    client.get("/")
    for _ in range(5):
        assert client.get("/").status_code == 429

    clock.now += 10
    assert client.get("/").status_code == 200


def test_rate_limit_retry_after_is_at_least_one_second(rate_limited_client):
    client, clock = rate_limited_client
    client.get("/")
    client.get("/")
    clock.now += 9.9

    assert client.get("/").headers["Retry-After"] == "1"


def test_rate_limit_window_slides(rate_limited_client):
    client, clock = rate_limited_client
    client.get("/")
    clock.now += 5
    client.get("/")

    clock.now += 5  # first request has left the window, second has not
    assert client.get("/").status_code == 200
    assert client.get("/").status_code == 429


# --- helpers ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "cover, expected",
    [
        (None, ""),
        ({}, ""),
        ({"url": ""}, ""),
        (
            {"url": "//images.igdb.com/igdb/image/upload/t_thumb/abc.jpg"},
            "https://images.igdb.com/igdb/image/upload/t_cover_big/abc.jpg",
        ),
    ],
)
def test_igdb_cover_url(cover, expected):
    assert _igdb_cover_url(cover) == expected


@pytest.mark.parametrize(
    "screenshot, expected",
    [
        (None, ""),
        ({}, ""),
        ({"url": ""}, ""),
        (
            {"url": "//images.igdb.com/igdb/image/upload/t_thumb/xyz.jpg"},
            "https://images.igdb.com/igdb/image/upload/t_screenshot_med_2x/xyz.jpg",
        ),
    ],
)
def test_igdb_screenshot_url(screenshot, expected):
    assert _igdb_screenshot_url(screenshot) == expected


@pytest.mark.parametrize(
    "age_ratings, expected",
    [
        (None, None),
        ([], None),
        ([{"category": 2, "rating": 10}], None),
        ([{"category": 1, "rating": 999}], None),
        (
            [{"category": 2, "rating": 10}, {"category": 1, "rating": 10}],
            GamesESRB.T,
        ),
    ],
)
def test_igdb_esrb_rating(age_ratings, expected):
    assert games_routes._igdb_esrb_rating(age_ratings) == expected


def test_game_from_row_builds_game(temp_db):
    database.seed_database()

    with closing(database.get_connection()) as connection:
        row = connection.execute("SELECT * FROM games WHERE id = 1").fetchone()
    game = games_routes.game_from_row(row)

    assert game.id == 1
    assert game.title == "The Legend of Zelda: Breath of the Wild"
    assert game.esrb == GamesESRB.E10


def test_search_games_without_filters_returns_requested_page(temp_db):
    database.seed_database()

    [game] = games_routes.search_games(skip=1, limit=1)

    assert game.id == 2


@pytest.mark.parametrize(
    "env, expected",
    [
        (None, ["http://localhost:3000", "http://127.0.0.1:3000"]),
        (" https://a.com , ,https://b.com,", ["https://a.com", "https://b.com"]),
        ("", []),
    ],
)
def test_get_cors_origins(monkeypatch, env, expected):
    if env is None:
        monkeypatch.delenv("CORS_ORIGINS", raising=False)
    else:
        monkeypatch.setenv("CORS_ORIGINS", env)

    assert main._get_cors_origins() == expected


# --- games: IGDB client ----------------------------------------------------------

IGDB_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
IGDB_GAME = {
    "id": 42,
    "name": "Portal",
    "first_release_date": 1191888000,  # 2007-10-09 UTC
    "summary": "Thinking with portals.",
    "cover": {"url": "//images.igdb.com/igdb/image/upload/t_thumb/cover.jpg"},
    "screenshots": [{"url": "//images.igdb.com/igdb/image/upload/t_thumb/shot.jpg"}],
    "genres": [{"name": "Puzzle"}, {"name": "Shooter"}],
    "platforms": [{"name": "PC"}, {"name": "Xbox 360"}],
    "rating": 88.5,
    "aggregated_rating": 90.0,
}


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://example.test")
            raise httpx.HTTPStatusError(
                "error", request=request, response=httpx.Response(self.status_code)
            )

    def json(self):
        return self.payload


class FakeIgdbClient:
    """Stands in for httpx.Client; answers each URL with a canned response."""

    def __init__(self, responses):
        self.responses = {IGDB_TOKEN_URL: FakeResponse({"access_token": "tok"}), **responses}
        self.requests = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return self.responses[url]


@pytest.fixture()
def igdb_credentials(monkeypatch):
    monkeypatch.setenv("IGDB_CLIENT_ID", "client-id")
    monkeypatch.setenv("IGDB_CLIENT_SECRET", "client-secret")


@pytest.fixture()
def fake_igdb(monkeypatch, igdb_credentials):
    """Install a FakeIgdbClient; call the returned function with {url: payload}."""

    def install(responses):
        client = FakeIgdbClient(
            {
                url: value if isinstance(value, FakeResponse) else FakeResponse(value)
                for url, value in responses.items()
            }
        )
        monkeypatch.setattr(games_routes.httpx, "Client", lambda **kwargs: client)
        return client

    return install


def assert_http_error(func, *args, status_code, detail):
    with pytest.raises(HTTPException) as exc_info:
        func(*args)
    assert exc_info.value.status_code == status_code
    assert exc_info.value.detail == detail


def test_fetch_igdb_token_uses_client_credentials(fake_igdb):
    client = fake_igdb({})

    assert games_routes._fetch_igdb_token(client, "cid", "secret") == "tok"
    url, kwargs = client.requests[0]
    assert url == IGDB_TOKEN_URL
    assert kwargs["params"] == {
        "client_id": "cid",
        "client_secret": "secret",
        "grant_type": "client_credentials",
    }


IMAGE_FETCHERS = [
    pytest.param(games_routes._fetch_ext_covers_games, "covers", id="covers"),
    pytest.param(games_routes._fetch_ext_artworks_games, "artworks", id="artworks"),
]


@pytest.mark.parametrize("fetch, endpoint", IMAGE_FETCHERS)
def test_fetch_images_short_circuits_on_empty_ids(monkeypatch, fetch, endpoint):
    monkeypatch.setattr(games_routes.httpx, "Client", None)  # must not be touched

    assert fetch([]) == []


@pytest.mark.parametrize("fetch, endpoint", IMAGE_FETCHERS)
@pytest.mark.parametrize("limit", [0, 501])
def test_fetch_images_rejects_out_of_range_limit(igdb_credentials, fetch, endpoint, limit):
    with pytest.raises(HTTPException) as exc_info:
        fetch([1], limit)

    assert exc_info.value.status_code == 400


@pytest.mark.parametrize("fetch, endpoint", IMAGE_FETCHERS)
def test_fetch_images_normalizes_urls_and_builds_query(fake_igdb, fetch, endpoint):
    url = f"https://api.igdb.com/v4/{endpoint}"
    client = fake_igdb(
        {url: [{"id": 1, "url": "//images.igdb.com/a.jpg"}, {"id": 2, "url": ""}, {"id": 3}]}
    )

    images = fetch([7, 8], 5)

    assert images == [
        {"id": 1, "url": "https://images.igdb.com/a.jpg"},
        {"id": 2, "url": ""},
        {"id": 3},
    ]
    request_url, kwargs = client.requests[-1]
    assert request_url == url
    assert kwargs["headers"]["Client-ID"] == "client-id"
    assert kwargs["headers"]["Authorization"] == "Bearer tok"
    assert "where game = (7,8); limit 5;" in kwargs["content"]


@pytest.mark.parametrize("fetch, endpoint", IMAGE_FETCHERS)
def test_fetch_images_wraps_http_errors(fake_igdb, fetch, endpoint):
    fake_igdb({f"https://api.igdb.com/v4/{endpoint}": FakeResponse([], status_code=500)})

    with pytest.raises(HTTPException) as exc_info:
        fetch([1])

    assert exc_info.value.status_code == 502


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda: games_routes._fetch_ext_covers_games([1]), id="covers"),
        pytest.param(lambda: games_routes._fetch_ext_artworks_games([1]), id="artworks"),
        pytest.param(lambda: games_routes._fetch_all_games_by_title("Portal", 10), id="title"),
        pytest.param(lambda: games_routes._fetch_all_platforms(10), id="platforms"),
        pytest.param(
            lambda: games_routes._fetch_all_platforms_versions(10),
            id="platform-versions",
        ),
        pytest.param(
            lambda: games_routes._fetch_all_esrb_ratings(10),
            id="esrb-ratings",
        ),
        pytest.param(lambda: games_routes._fetch_all_games_by_date(2024, 1, 1, 10, 0), id="by-date"),
        pytest.param(lambda: games_routes._fetch_next_releases(10), id="next-releases"),
    ],
)
@pytest.mark.parametrize("missing", ["IGDB_CLIENT_ID", "IGDB_CLIENT_SECRET"])
def test_igdb_fetchers_require_credentials(igdb_credentials, monkeypatch, call, missing):
    monkeypatch.delenv(missing)

    assert_http_error(call, status_code=503, detail="IGDB credentials are not configured")


@pytest.mark.parametrize("title", ["", "   "])
def test_fetch_games_by_title_requires_title(igdb_credentials, title):
    assert_http_error(
        games_routes._fetch_all_games_by_title, title, 10,
        status_code=400, detail="A game title is required",
    )


def test_fetch_games_by_title_maps_igdb_fields(fake_igdb):
    igdb_game = {
        **IGDB_GAME,
        "game_modes": [{"id": 1, "name": "Single Player"}],
        "age_ratings": [{"category": 2, "rating": 2}, {"category": 1, "rating": 10}],
        "screenshots": [
            {"url": "//images.igdb.com/igdb/image/upload/t_thumb/shot.jpg"},
            {"url": "//images.igdb.com/igdb/image/upload/t_thumb/shot2.jpg"},
        ],
        "involved_companies": [
            {"developer": True, "publisher": False, "company": {"name": "Valve"}},
            {"developer": False, "publisher": True, "company": {"name": "Valve"}},
        ],
        "websites": [{"category": 1, "url": "https://www.thinkwithportals.com/"}],
        "videos": [{"video_id": "abc123"}],
    }
    client = fake_igdb({"https://api.igdb.com/v4/games": [igdb_game]})

    [game] = games_routes._fetch_all_games_by_title('  Portal "2" ', 3)

    assert game.id == 42
    assert game.title == "Portal"
    assert game.genre == "Puzzle, Shooter"
    assert game.release_year == 2007
    assert game.release_date == "2007-10-09"
    assert game.description == "Thinking with portals."
    assert game.gamemodes == "Single Player"
    assert game.cover_image_url == game.image_url == (
        "https://images.igdb.com/igdb/image/upload/t_cover_big/cover.jpg"
    )
    assert game.screenshot_url == (
        "https://images.igdb.com/igdb/image/upload/t_screenshot_med_2x/shot.jpg"
    )
    assert game.screenshots == [
        "https://images.igdb.com/igdb/image/upload/t_screenshot_med_2x/shot.jpg",
        "https://images.igdb.com/igdb/image/upload/t_screenshot_med_2x/shot2.jpg",
    ]
    assert game.developer_name == "Valve"
    assert game.publisher_name == "Valve"
    assert game.website_url == "https://www.thinkwithportals.com/"
    assert game.trailer_url == "https://www.youtube.com/watch?v=abc123"
    assert game.platforms == "PC, Xbox 360"
    assert (game.user_rating, game.critic_rating) == (88.5, 90.0)
    assert game.esrb == GamesESRB.T
    assert game.model_dump(mode="json")["esrb"] == "t"
    query = client.requests[-1][1]["content"]
    assert "game_modes.id,game_modes.name" in query
    assert "age_ratings.category" in query
    assert "age_ratings.rating" in query
    assert "websites.url" in query
    assert "videos.video_id" in query
    assert "involved_companies.company.name" in query
    assert 'where name ~ "Portal \\"2\\""; ' in query  # stripped and JSON-escaped
    assert "limit 3;" in query


def test_fetch_games_by_title_wraps_http_errors(fake_igdb):
    fake_igdb(
        {"https://api.igdb.com/v4/games": FakeResponse([], status_code=500)}
    )

    assert_http_error(
        games_routes._fetch_all_games_by_title,
        "Portal",
        10,
        status_code=502,
        detail="Unable to fetch all releases by title from IGDB",
    )


def test_fetch_games_by_title_tolerates_missing_screenshots(fake_igdb):
    game = {key: value for key, value in IGDB_GAME.items() if key != "screenshots"}
    fake_igdb({"https://api.igdb.com/v4/games": [game]})

    [result] = games_routes._fetch_all_games_by_title("Portal", 10)

    assert result.screenshot_url == ""


def test_fetch_platforms_fills_defaults_for_missing_fields(fake_igdb):
    fake_igdb(
        {
            "https://api.igdb.com/v4/platforms": [
                {"name": "PC", "slug": "win", "generation": 1, "created_at": 1700000000},
                {},
            ]
        }
    )

    full, empty = games_routes._fetch_all_platforms(10)

    assert (full.name, full.slug, full.generation) == ("PC", "win", 1)
    assert full.created_at.date().isoformat() == "2023-11-14"
    assert empty.name == empty.slug == empty.url == ""
    assert empty.generation == empty.platform_family == 0
    assert empty.created_at.year == 1970


def test_fetch_platform_versions_expands_related_fields(fake_igdb):
    logo = {
        "alpha_channel": False,
        "animated": False,
        "checksum": "logo-checksum",
        "height": 64,
        "image_id": "logo-image",
        "url": "//images.igdb.com/logo.jpg",
        "width": 64,
    }
    company = {
        "checksum": "company-checksum",
        "comment": "",
        "company": 12,
        "developer": True,
        "manufacturer": False,
    }
    release_date = {
        "checksum": "release-checksum",
        "created_at": 1700000000,
        "date": 1700000000,
        "date_format": 0,
        "human": "Nov 14, 2023",
        "m": 11,
        "release_region": 1,
        "updated_at": 1700000000,
        "y": 2023,
    }
    client = fake_igdb(
        {
            "https://api.igdb.com/v4/platform_versions": [
                {
                    "checksum": "version-checksum",
                    "companies": [company],
                    "name": "PC",
                    "platform_logo": logo,
                    "platform_version_release_dates": [release_date],
                    "summary": "Platform summary",
                    "url": "https://example.test/platform-version",
                }
            ]
        }
    )

    [version] = games_routes._fetch_all_platforms_versions(1)

    assert version.platform_logo.url == "//images.igdb.com/logo.jpg"
    assert version.companies[0].company == 12
    assert version.platform_version_release_dates[0].human == "Nov 14, 2023"
    assert version.platform_version_release_dates[0].platform_version is None
    assert version.url == "https://example.test/platform-version"
    query = client.requests[-1][1]["content"]
    assert "platform_logo.url" in query
    assert "companies.company" in query
    assert "platform_version_release_dates.date" in query


def test_fetch_platforms_rejects_non_list_response(fake_igdb):
    fake_igdb({"https://api.igdb.com/v4/platforms": {"message": "nope"}})

    assert_http_error(
        games_routes._fetch_all_platforms, 10,
        status_code=502, detail="Unable to fetch all platforms from IGDB",
    )


def test_fetch_games_by_date_returns_page_with_total(fake_igdb):
    client = fake_igdb(
        {
            "https://api.igdb.com/v4/games": [
                {**IGDB_GAME, "game_modes": [{"id": 1, "name": "Single Player"}]}
            ],
            "https://api.igdb.com/v4/games/count": {"count": 57},
        }
    )

    page = games_routes._fetch_all_games_by_date(2007, 10, 1, 5, 20)

    assert page.total == 57
    assert page.page_size == 5
    assert [game.id for game in page.items] == [42]
    assert page.items[0].gamemodes[0].id == 1
    assert page.items[0].gamemodes[0].name == "Single Player"
    (_, games_request), (_, count_request) = client.requests[-2:]
    assert "game_modes.id,game_modes.name" in games_request["content"]
    assert count_request["content"].startswith("where first_release_date >= ")
    assert count_request["content"] in games_request["content"]
    assert "offset 20; limit 5;" in games_request["content"]


def test_fetch_games_by_date_defaults_total_to_zero(fake_igdb):
    fake_igdb(
        {
            "https://api.igdb.com/v4/games": [],
            "https://api.igdb.com/v4/games/count": {},
        }
    )

    assert games_routes._fetch_all_games_by_date(2024, 1, 1, 10, 0).total == 0


def test_fetch_games_by_date_wraps_count_http_errors(fake_igdb):
    fake_igdb(
        {
            "https://api.igdb.com/v4/games": [],
            "https://api.igdb.com/v4/games/count": FakeResponse(
                {}, status_code=500
            ),
        }
    )

    assert_http_error(
        games_routes._fetch_all_games_by_date,
        2024,
        1,
        1,
        10,
        0,
        status_code=502,
        detail="Unable to fetch all releases from IGDB",
    )


def test_fetch_next_releases_queries_future_games(fake_igdb, monkeypatch):
    monkeypatch.setattr(games_routes.time, "time", lambda: 1700000000.9)
    client = fake_igdb({"https://api.igdb.com/v4/games": [IGDB_GAME]})

    [game] = games_routes._fetch_next_releases(4)

    assert game.title == "Portal"
    query = client.requests[-1][1]["content"]
    assert "where first_release_date > 1700000000; " in query
    assert "limit 4;" in query


def test_fetch_next_releases_wraps_token_without_access_token(fake_igdb):
    fake_igdb({IGDB_TOKEN_URL: {}})

    assert_http_error(
        games_routes._fetch_next_releases, 10,
        status_code=502, detail="Unable to fetch next releases from IGDB",
    )


def test_fetch_esrb_ratings_maps_response(fake_igdb):
    client = fake_igdb(
        {
            "https://api.igdb.com/v4/age_rating_categories": [
                {"organization": 1, "rating": 10},
                {"organization": None, "rating": None},
            ]
        }
    )

    ratings = games_routes._fetch_all_esrb_ratings(2)

    assert [rating.model_dump() for rating in ratings] == [
        {"organization": 1, "rating": 10},
        {"organization": "", "rating": ""},
    ]
    assert client.requests[-1][1]["content"] == "fields organization,rating; limit 2;"


def test_fetch_esrb_ratings_rejects_non_list_response(fake_igdb):
    fake_igdb({"https://api.igdb.com/v4/age_rating_categories": {"message": "nope"}})

    assert_http_error(
        games_routes._fetch_all_esrb_ratings,
        10,
        status_code=502,
        detail="Unable to fetch all ESRB ratings from IGDB",
    )


def test_fetch_platform_versions_rejects_non_list_response(fake_igdb):
    fake_igdb({"https://api.igdb.com/v4/platform_versions": {"message": "nope"}})

    assert_http_error(
        games_routes._fetch_all_platforms_versions,
        1,
        status_code=502,
        detail="Unable to fetch all platform versions from IGDB",
    )


@pytest.mark.parametrize(
    "route, dependency, args, expected_args",
    [
        (
            games_routes.list_all_releases,
            "_fetch_all_games_by_date",
            (2024, 1, 2, 5, 20),
            (2024, 1, 2, 20, 5, games_routes.ReleaseSort.RELEASE_DATE, None),
        ),
        (
            games_routes.list_all_releases_by_title,
            "_fetch_all_games_by_title",
            ("Portal", 3),
            ("Portal", 3),
        ),
        (
            games_routes.list_all_covers,
            "_fetch_ext_covers_games",
            ([7, 8], 5),
            ([7, 8], 5),
        ),
        (
            games_routes.list_all_artworks,
            "_fetch_ext_artworks_games",
            ([7, 8], 5),
            ([7, 8], 5),
        ),
        (games_routes.list_next_releases, "_fetch_next_releases", (4,), (4,)),
        (games_routes.list_esrb_ratings, "_fetch_all_esrb_ratings", (10,), (10,)),
        (games_routes.fetch_platforms_games, "_fetch_all_platforms", (6,), (6,)),
        (
            games_routes.fetch_platforms_versions_games,
            "_fetch_all_platforms_versions",
            (6,),
            (6,),
        ),
    ],
)
def test_game_route_delegates_to_igdb_fetcher(
    monkeypatch, route, dependency, args, expected_args
):
    expected = object()
    calls = []

    def fetch(*received_args):
        calls.append(received_args)
        return expected

    monkeypatch.setattr(games_routes, dependency, fetch)

    assert route(*args) is expected
    assert calls == [expected_args]


def test_game_autoincrement_routes_use_database_helpers(temp_db):
    database.seed_database()

    assert games_routes.fetch_games_autoincrement() == {
        "table": "games",
        "next_id": 4,
    }
    assert games_routes.reset_games_autoincrement() == {
        "table": "games",
        "next_id": 4,
    }


# --- schemas ---------------------------------------------------------------------


def test_game_create_defaults():
    game = GameCreate(
        title="Portal",
        genre="Puzzle",
        release_year=2007,
        esrb=None,
    )

    assert game.platforms == Gameplatforms.PC
    assert game.gamemodes == GameModes.ALL
    assert game.editions == GameEdition.STANDARD
    assert game.esrb is None
    assert game.wishlisted is False
    assert game.user_rating == game.critic_rating == game.hoursplayed == 0


def test_game_create_accepts_enum_lists_and_free_text():
    game = GameCreate(
        title="Portal",
        genre="Puzzle",
        release_year=2007,
        platforms=["PC", "Xbox 360"],
        esrb="T",
    )

    assert game.platforms == [Gameplatforms.PC, Gameplatforms.XBOX_360]
    assert game.esrb == GamesESRB.T
    assert game.model_dump(mode="json")["esrb"] == "t"


def test_game_create_requires_core_fields():
    with pytest.raises(ValueError):
        GameCreate(title="Portal")


def test_achievement_create_defaults_and_status_validation():
    achievement = AchievementCreate(title="First Blood")

    assert achievement.status is AchievementStatus.LOCKED
    assert achievement.unlocked is False
    with pytest.raises(ValueError):
        AchievementCreate(title="First Blood", status="Half-unlocked")


def test_achievement_create_type_defaults_and_validation():
    achievement = AchievementCreate(title="First Blood", achievement_type="Gold")

    assert AchievementCreate(title="First Blood").achievement_type is AchievementType.BRONZE
    assert achievement.achievement_type is AchievementType.GOLD
    with pytest.raises(ValueError):
        AchievementCreate(title="First Blood", achievement_type="Diamond")


def test_achievement_requires_ids():
    achievement = Achievement(title="First Blood", achievement_id=1, game_id=2)

    assert (achievement.achievement_id, achievement.game_id) == (1, 2)
    with pytest.raises(ValueError):
        Achievement(title="First Blood", achievement_id=1)


@pytest.mark.parametrize(
    "esrb, expected",
    [
        ("M", GamesESRB.M),
        ("m", GamesESRB.M),
        ("CERO_A", GamesESRB.CERO_A),
        ("1", GamesESRB.Three),
        (12, GamesESRB.AO),
        (len(GamesESRB), list(GamesESRB)[-1]),
        (GamesESRB.E10, GamesESRB.E10),
        (None, None),
    ],
)
def test_game_create_parses_esrb_names_values_and_igdb_ids(esrb, expected):
    game = GameCreate(title="Portal", genre="Puzzle", release_year=2007, esrb=esrb)

    assert game.esrb == expected
    assert game.model_dump(mode="json")["esrb"] == (
        expected.value if expected is not None else None
    )


@pytest.mark.parametrize("esrb", ["0", 0, 999, "unknown"])
def test_game_create_rejects_unknown_esrb(esrb):
    with pytest.raises(ValueError):
        GameCreate(title="Portal", genre="Puzzle", release_year=2007, esrb=esrb)


def test_game_create_esrb_json_schema_lists_every_rating():
    esrb_schema = GameCreate.model_json_schema()["properties"]["esrb"]

    assert esrb_schema["example"] == GamesESRB.E.value
    assert [option["const"] for option in esrb_schema["oneOf"]] == [
        rating.value for rating in GamesESRB
    ]


def test_game_create_accepts_gamemode_models_and_edition_lists():
    game = GameCreate(
        title="Portal",
        genre="Puzzle",
        release_year=2007,
        gamemodes=[{"id": 1, "name": "Single player"}],
        editions=["Deluxe", "Game of the Year"],
    )

    assert game.gamemodes[0].id == 1
    assert game.gamemodes[0].name == "Single player"
    assert game.editions == [GameEdition.DELUXE, GameEdition.GAME_OF_THE_YEAR]


def test_game_create_screenshots_default_is_not_shared():
    first = GameCreate(title="Portal", genre="Puzzle", release_year=2007)
    second = GameCreate(title="Portal 2", genre="Puzzle", release_year=2011)

    first.screenshots.append("shot.jpg")

    assert second.screenshots == []


def test_game_requires_id():
    assert Game(id=7, title="Portal", genre="Puzzle", release_year=2007).id == 7
    with pytest.raises(ValueError):
        Game(title="Portal", genre="Puzzle", release_year=2007)


def test_schemas_module_reexports_route_schemas():
    from routes.achievements import schemas as achievement_schemas
    from routes.games import schemas as game_schemas

    assert shared_schemas.__all__ == [
        "Achievement",
        "AchievementCreate",
        "AchievementStatus",
        "Game",
        "GameCreate",
        "GameEdition",
        "GameModes",
        "Gameplatforms",
        "GamesESRB",
    ]
    for name in shared_schemas.__all__:
        source = achievement_schemas if hasattr(achievement_schemas, name) else game_schemas
        assert getattr(shared_schemas, name) is getattr(source, name)
