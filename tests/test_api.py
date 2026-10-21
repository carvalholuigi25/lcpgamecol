import pytest
from fastapi.testclient import TestClient

import backend.auth.auth as auth
import backend.database.database as database
from main import app

GAME = {
    "title": "Portal 2",
    "genre": "Puzzle",
    "platforms": "PC",
    "release_year": 2011,
    "description": "A cooperative puzzle game.",
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test.db")
    auth._login_attempts.clear()
    database.initialize_database()
    database.seed_database()
    with TestClient(app) as test_client:
        app.middleware_stack.app.requests.clear()
        yield test_client


@pytest.fixture()
def auth_headers(client):
    response = client.post(
        "/auth/token",
        data={"username": "admin", "password": "1234"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture()
def viewer_headers(client, monkeypatch):
    monkeypatch.setitem(auth.AUTH_USERS, "viewer", ("viewer-pass", auth.ROLE_VIEWER))
    response = client.post(
        "/auth/token",
        data={"username": "viewer", "password": "viewer-pass"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_root_and_authentication(client, auth_headers):
    client.cookies.clear()
    root = client.get("/", follow_redirects=False)
    assert root.status_code == 302
    assert root.headers["location"] == "/library"
    assert client.get("/health").status_code == 401
    assert client.get("/health", headers=auth_headers).json() == {
        "message": "Games API is running"
    }
    assert client.get("/games").status_code == 401
    assert client.get("/users").status_code == 401


def test_custom_page_routes_preserve_games_api_route(client, auth_headers):
    library = client.get("/library")
    releases = client.get("/library/releases")
    admin = client.get("/admin")

    assert library.status_code == 200
    assert 'id="login-form"' in library.text
    for control_id in ("first-page", "previous-page", "page-selector", "next-page", "last-page"):
        assert f'id="{control_id}"' in library.text
    assert releases.status_code == 200
    assert 'id="login-form"' in releases.text
    for page in (library, releases):
        assert "/nmodules/video.js/dist/video-js.min.css" in page.text
        assert "/nmodules/video.js/dist/video.min.js" in page.text
        assert "/nmodules/videojs-youtube/dist/Youtube.min.js" in page.text
        assert 'id="details-trailer-section"' in page.text
        assert 'id="details-screenshots-section"' in page.text
        assert 'id="details-requirements-warning"' in page.text
    for asset in (
        "/nmodules/video.js/dist/video-js.min.css",
        "/nmodules/video.js/dist/video.min.js",
        "/nmodules/videojs-youtube/dist/Youtube.min.js",
    ):
        assert client.get(asset).status_code == 200
    assert admin.status_code == 200
    assert 'id="login-view"' in admin.text
    assert client.get("/pages/games/games.html").text == library.text
    assert client.get("/pages/games/games_releases.html").text == releases.text
    assert client.get("/pages/admin/admin.html").text == admin.text
    assert client.get("/games", headers=auth_headers).status_code == 200

    response = client.post(
        "/auth/token",
        data={"username": "admin", "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect username or password"


def test_error_pages_are_served_for_browser_requests(client, viewer_headers):
    headers = {"Accept": "text/html"}
    client.cookies.clear()

    unauthorized = client.get("/health", headers=headers)
    forbidden = client.get("/admin/dashboard", headers=headers | viewer_headers)
    not_found = client.get("/missing-page", headers=headers)

    assert unauthorized.status_code == 401
    assert "401" in unauthorized.text
    assert forbidden.status_code == 403
    assert "403" in forbidden.text
    assert not_found.status_code == 404
    assert "404" in not_found.text

    api_unauthorized = client.get("/health", headers={"Accept": "application/json"})
    assert api_unauthorized.status_code == 401
    assert "detail" in api_unauthorized.json()


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 429, 500])
def test_custom_error_page_files_are_available(client, status_code):
    response = client.get(f"/pages/errors/{status_code}.html")

    assert response.status_code == 200
    assert str(status_code) in response.text
    if status_code == 429:
        assert 'data-retry-after="0"' in response.text
    else:
        assert 'id="retry-timer"' not in response.text


def test_login_locks_after_three_failed_attempts(client, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(auth, "_monotonic", lambda: now[0])

    for _ in range(2):
        response = client.post(
            "/auth/token", data={"username": "admin", "password": "wrong"}
        )
        assert response.status_code == 401

    locked = client.post(
        "/auth/token", data={"username": "admin", "password": "wrong"}
    )
    assert locked.status_code == 429
    assert locked.headers["retry-after"] == "60"
    assert "3 failed attempts" in locked.json()["detail"]

    correct_password = client.post(
        "/auth/token", data={"username": "admin", "password": "1234"}
    )
    assert correct_password.status_code == 429

    now[0] += 60
    unlocked = client.post(
        "/auth/token", data={"username": "admin", "password": "1234"}
    )
    assert unlocked.status_code == 200


def test_cors_and_security_policy_headers(client):
    preflight = client.options(
        "/games",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert preflight.headers["access-control-allow-credentials"] == "true"

    response = client.get("/", headers={"Origin": "http://localhost:3000"})
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"


def test_users_endpoint_requires_authentication(client, auth_headers):
    response = client.get("/users", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"username": "admin"}


def test_admin_dashboard_summary_is_admin_only(client, auth_headers, viewer_headers):
    summary = client.get("/admin/dashboard", headers=auth_headers)

    assert summary.status_code == 200
    data = summary.json()
    assert data["overview"] == {
        "games": 3,
        "achievements": 4,
        "unlocked_achievements": 0,
        "achievement_completion": 0,
        "wishlist": 2,
        "hours_played": 180.5,
        "average_user_rating": 9.7,
        "average_critic_rating": 9.4,
    }
    assert data["achievement_types"] == [
        {"label": "Platinum", "count": 1},
        {"label": "Gold", "count": 1},
        {"label": "Silver", "count": 1},
        {"label": "Bronze", "count": 1},
    ]
    assert data["release_years"] == [
        {"label": "2017", "count": 1},
        {"label": "2018", "count": 2},
    ]
    assert data["platforms"][0] == {"label": "PlayStation 4", "count": 2}
    assert len(data["recent_games"]) == 3
    client.cookies.clear()
    assert client.get("/admin/dashboard").status_code == 401
    assert client.get("/admin/dashboard", headers=viewer_headers).status_code == 403


def test_admin_dashboard_page_and_assets_are_served(client):
    page = client.get("/pages/admin/admin.html")

    assert page.status_code == 200
    assert 'id="release-chart"' in page.text
    assert 'id="achievement-type-chart"' in page.text
    assert 'id="game-record-form"' in page.text
    assert 'id="achievement-record-form"' in page.text
    assert 'id="new-game-button"' in page.text
    assert 'id="new-achievement-button"' in page.text
    assert 'id="edit-game-button"' in page.text
    assert 'id="edit-achievement-button"' in page.text
    assert 'id="delete-game-button"' in page.text
    assert 'id="delete-achievement-button"' in page.text
    assert 'id="toast-region"' in page.text
    assert 'id="live-clock"' in page.text
    assert 'id="theme-selector"' in page.text
    assert 'id="page-loader"' in page.text
    assert 'data-lockout' in page.text
    assert 'src="/public/scripts/loading.js"' in page.text
    assert 'src="/public/scripts/preferences.js"' in page.text
    assert client.get("/public/scripts/admin.js").status_code == 200
    assert client.get("/public/scripts/loading.js").status_code == 200
    assert client.get("/public/scripts/preferences.js").status_code == 200
    assert client.get("/public/styles/css/admin.css").status_code == 200
    games_page = client.get("/pages/games/games.html").text
    releases_page = client.get("/pages/games/games_releases.html").text
    for shelf_page in (games_page, releases_page):
        assert 'href="/admin"' in shelf_page
        assert 'id="details-achievements-list"' in shelf_page
        assert 'id="live-clock"' in shelf_page
        assert 'id="theme-selector"' in shelf_page
        assert 'id="page-loader"' in shelf_page
        assert 'data-lockout' in shelf_page
        assert 'src="/public/scripts/loading.js"' in shelf_page
        assert 'src="/public/scripts/preferences.js"' in shelf_page


@pytest.mark.parametrize("theme", ["sunsetvibes", "cyber-retro", "rgb"])
def test_site_pages_offer_the_api_docs_themes(client, theme):
    pages = ("/pages/admin/admin.html", "/pages/games/games.html", "/pages/games/games_releases.html")
    for path in pages:
        assert f'<option value="{theme}">' in client.get(path).text

    assert f'"{theme}"' in client.get("/public/scripts/preferences.js").text
    for stylesheet in ("/public/styles/css/games.css", "/public/styles/css/admin.css"):
        assert f"body[data-theme={theme}]" in client.get(stylesheet).text


def test_admin_dashboard_page_settings_are_available(client):
    page = client.get("/pages/admin/admin.html")

    assert page.status_code == 200
    assert "Page settings" in page.text
    assert 'id="settings-panel"' in page.text
    assert 'id="settings-form"' in page.text


def test_swagger_ui_persists_authorization(client):
    config = client.get("/docs").text

    assert "bootstrap@6.0.0-alpha.1" in config
    assert "api-docs-header" in config
    assert 'id="swagger-theme"' in config
    assert 'value="white"' in config
    assert 'value="dark"' in config
    assert 'value="auto"' in config
    assert 'value="sunsetvibes"' in config
    assert 'value="cyber-retro"' in config
    assert 'value="rgb"' in config
    assert "games-api-swagger-theme" in config
    assert 'href="/public/styles/css/swagger.css"' in config
    assert '"deepLinking": true' in config
    assert '"displayRequestDuration": true' in config
    assert '"filter": true' in config
    assert '"persistAuthorization": true' in config
    assert '"tryItOutEnabled": false' in config

    stylesheet = client.get("/public/styles/css/swagger.css")
    assert stylesheet.status_code == 200
    assert ".swagger-ui" in stylesheet.text
    assert "body[data-theme=cyber-retro]" in stylesheet.text
    assert "body[data-theme=rgb]" in stylesheet.text
    assert "@keyframes rgb-flow" in stylesheet.text


def test_login_persists_cookie_session(client):
    response = client.post(
        "/auth/token",
        data={"username": "admin", "password": "1234"},
    )

    assert response.status_code == 200
    assert response.cookies.get("access_token") == response.json()["access_token"]
    assert response.json()["refresh_token"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert client.get("/games").status_code == 200


def test_refresh_token_endpoint_is_protected(client):
    assert client.post("/auth/refresh").status_code == 401

    login = client.post(
        "/auth/token",
        data={"username": "admin", "password": "1234"},
    )
    refresh_token = login.json()["refresh_token"]

    refreshed = client.post(
        "/auth/refresh",
        headers={"Authorization": f"Bearer {refresh_token}"},
    )

    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]
    assert client.get(
        "/games",
        headers={"Authorization": f"Bearer {refreshed.json()['access_token']}"},
    ).status_code == 200
    assert client.post(
        "/auth/refresh",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    ).status_code == 401


def test_logout_endpoint_is_protected_and_clears_cookie(client):
    assert client.post("/auth/logout").status_code == 401

    login = client.post(
        "/auth/token",
        data={"username": "admin", "password": "1234"},
    )
    assert client.get("/games").status_code == 200

    logout = client.post("/auth/logout")

    assert logout.status_code == 204
    assert "Max-Age=0" in logout.headers["set-cookie"]
    assert client.get("/games").status_code == 401
    assert client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    ).status_code == 204


def test_game_crud_and_search(client, auth_headers):
    response = client.get("/games", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) == 3

    created = client.post("/games", json=GAME, headers=auth_headers)
    assert created.status_code == 201
    game_id = created.json()["id"]
    assert created.json()["title"] == GAME["title"]

    searched = client.get(
        "/games/search?title=portal&release_year=2011", headers=auth_headers
    )
    assert [game["id"] for game in searched.json()] == [game_id]

    updated_game = {**GAME, "title": "Portal 2: Cooperative Edition"}
    updated = client.put(
        f"/games/{game_id}", json=updated_game, headers=auth_headers
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == updated_game["title"]

    assert client.get(f"/games/{game_id}", headers=auth_headers).status_code == 200
    assert client.delete(f"/games/{game_id}", headers=auth_headers).status_code == 204
    assert client.get(f"/games/{game_id}", headers=auth_headers).status_code == 404


def test_game_system_requirements_round_trip(client, auth_headers):
    game = {
        **GAME,
        "minimum_system_requirements": "Windows 10; 8 GB RAM; DirectX 11 GPU",
        "recommended_system_requirements": "Windows 11; 16 GB RAM; dedicated GPU",
    }
    created = client.post("/games", json=game, headers=auth_headers)

    assert created.status_code == 201
    game_id = created.json()["id"]
    assert created.json()["minimum_system_requirements"] == game[
        "minimum_system_requirements"
    ]
    assert created.json()["recommended_system_requirements"] == game[
        "recommended_system_requirements"
    ]
    assert client.get(f"/games/{game_id}", headers=auth_headers).json()[
        "minimum_system_requirements"
    ] == game["minimum_system_requirements"]

    updated_game = {
        **game,
        "minimum_system_requirements": "Updated minimum requirement",
        "recommended_system_requirements": None,
    }
    updated = client.put(
        f"/games/{game_id}", json=updated_game, headers=auth_headers
    )

    assert updated.status_code == 200
    assert updated.json()["minimum_system_requirements"] == "Updated minimum requirement"
    assert updated.json()["recommended_system_requirements"] is None


def test_game_developer_publisher_website_trailer_and_screenshots_round_trip(
    client, auth_headers
):
    game = {
        **GAME,
        "developer_name": "Valve",
        "publisher_name": "Valve",
        "website_url": "https://www.thinkwithportals.com/",
        "trailer_url": "https://www.youtube.com/watch?v=abc123",
        "screenshots": [
            "https://cdn.example.com/portal-1.jpg",
            "https://cdn.example.com/portal-2.jpg",
        ],
    }
    created = client.post("/games", json=game, headers=auth_headers)

    assert created.status_code == 201
    game_id = created.json()["id"]
    assert {key: created.json()[key] for key in game if key not in GAME} == {
        key: game[key] for key in game if key not in GAME
    }
    assert client.get(f"/games/{game_id}", headers=auth_headers).json()[
        "screenshots"
    ] == game["screenshots"]

    updated_game = {
        **game,
        "developer_name": "Valve Corporation",
        "screenshots": ["https://cdn.example.com/portal-updated.jpg"],
    }
    updated = client.put(
        f"/games/{game_id}", json=updated_game, headers=auth_headers
    )

    assert updated.status_code == 200
    assert updated.json()["developer_name"] == "Valve Corporation"
    assert updated.json()["publisher_name"] == game["publisher_name"]
    assert updated.json()["website_url"] == game["website_url"]
    assert updated.json()["trailer_url"] == game["trailer_url"]
    assert updated.json()["screenshots"] == updated_game["screenshots"]


def test_esrb_ratings_endpoint_returns_structured_data(client, auth_headers, monkeypatch):
    import httpx2 as httpx

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, **kwargs):
            if "twitch.tv" in url:
                return FakeResponse({"access_token": "token"})
            return FakeResponse([
                {"organization": 1, "rating": 1},
                {"organization": 4, "rating": 4},
            ])

    monkeypatch.setenv("IGDB_CLIENT_ID", "client-id")
    monkeypatch.setenv("IGDB_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(httpx, "Client", FakeClient)

    response = client.get("/games/esrb-ratings?limit=10", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == [
        {"organization": 1, "rating": 1},
        {"organization": 4, "rating": 4},
    ]


def test_reset_autoincrement_keeps_existing_ids_safe(client, auth_headers):
    game = client.post("/games", json=GAME, headers=auth_headers).json()
    achievement = client.post(
        f"/games/{game['id']}/achievements",
        json={"title": "Reset test"},
        headers=auth_headers,
    ).json()
    assert client.delete(
        f"/games/{game['id']}/achievements/{achievement['achievement_id']}",
        headers=auth_headers,
    ).status_code == 204
    assert client.delete(f"/games/{game['id']}", headers=auth_headers).status_code == 204

    assert client.post("/games/reset-autoincrement", headers=auth_headers).json() == {
        "table": "games",
        "next_id": game["id"],
    }
    assert client.post(
        "/achievements/reset-autoincrement", headers=auth_headers
    ).json() == {
        "table": "achievements",
        "next_id": achievement["achievement_id"],
    }

    next_game = client.post("/games", json=GAME, headers=auth_headers).json()
    next_achievement = client.post(
        f"/games/{next_game['id']}/achievements",
        json={"title": "Next achievement"},
        headers=auth_headers,
    ).json()
    assert next_game["id"] == game["id"]
    assert next_achievement["achievement_id"] == achievement["achievement_id"]


def test_external_search_uses_query_parameter(client, auth_headers, monkeypatch):
    import routes.games.routes as games_routes

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [{"id": 42, "name": "Portal", "first_release_date": 1191456000}]

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, **kwargs):
            if "twitch.tv" in url:
                return type(
                    "TokenResponse",
                    (),
                    {
                        "raise_for_status": lambda self: None,
                        "json": lambda self: {"access_token": "token"},
                    },
                )()
            assert url == "https://api.igdb.com/v4/games"
            assert 'where name ~ "Portal";' in kwargs["content"]
            return FakeResponse()

    monkeypatch.setenv("IGDB_CLIENT_ID", "client-id")
    monkeypatch.setenv("IGDB_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(games_routes.httpx, "Client", lambda **kwargs: FakeClient())

    response = client.get(
        "/games/external-search?query=Portal&limit=1", headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json()[0]["title"] == "Portal"


def test_game_release_date_is_a_date_field(client, auth_headers):
    game = {**GAME, "release_date": "2017-03-03"}

    response = client.post("/games", json=game, headers=auth_headers)

    assert response.status_code == 201
    assert response.json()["release_year"] == 2011
    assert response.json()["release_date"] == "2017-03-03"


def test_collection_pagination(client, auth_headers):
    page = client.get("/games?skip=1&limit=1", headers=auth_headers)
    assert page.status_code == 200
    assert [game["id"] for game in page.json()] == [2]

    games_page = client.get("/games/page?skip=1&limit=1", headers=auth_headers)
    assert games_page.status_code == 200
    assert [game["id"] for game in games_page.json()["items"]] == [2]
    assert games_page.json()["total"] == 3
    assert games_page.json()["page_size"] == 1

    search_page = client.get(
        "/games/search?genre=Action-adventure&skip=1&limit=1",
        headers=auth_headers,
    )
    assert search_page.status_code == 200
    assert [game["id"] for game in search_page.json()] == [2]

    assert client.get("/games?limit=0", headers=auth_headers).status_code == 422
    assert client.get("/games?skip=-1", headers=auth_headers).status_code == 422


def test_next_releases_fetches_future_games(client, auth_headers, monkeypatch):
    import routes.games.routes as games_routes

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, **kwargs):
            if "twitch.tv" in url:
                return FakeResponse({"access_token": "test-token"})
            assert "first_release_date > " in kwargs["content"]
            assert "sort first_release_date asc" in kwargs["content"]
            assert kwargs["content"].endswith("limit 1;")
            return FakeResponse(
                [
                    {
                        "id": 99,
                        "name": "Future Game",
                        "first_release_date": 1893456000,
                        "summary": "Coming soon.",
                        "genres": [{"name": "Adventure"}],
                        "platforms": [{"name": "PC"}],
                        "cover": {"url": "//images.igdb.com/cover.jpg"},
                    }
                ]
            )

    monkeypatch.setenv("IGDB_CLIENT_ID", "client-id")
    monkeypatch.setenv("IGDB_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(games_routes.httpx, "Client", lambda **kwargs: FakeClient())

    response = client.get(
        "/games/next-releases?limit=1", headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json()[0]["title"] == "Future Game"
    assert response.json()[0]["release_date"] == "2030-01-01"
    assert response.json()[0]["cover_image_url"] == "https://images.igdb.com/cover.jpg"


def test_fetch_ext_covers_games_uses_igdb_covers_endpoint(monkeypatch):
    import routes.games.routes as games_routes

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, **kwargs):
            if "twitch.tv" in url:
                return FakeResponse({"access_token": "test-token"})
            assert url == "https://api.igdb.com/v4/covers"
            assert "where game = (42);" in kwargs["content"]
            assert kwargs["content"].endswith("limit 1;")
            assert kwargs["headers"]["Authorization"] == "Bearer test-token"
            return FakeResponse([{"id": 7, "url": "//images.igdb.com/cover.jpg"}])

    monkeypatch.setenv("IGDB_CLIENT_ID", "client-id")
    monkeypatch.setenv("IGDB_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(games_routes.httpx, "Client", lambda **kwargs: FakeClient())

    covers = games_routes._fetch_ext_covers_games([42], limit=1)

    assert covers == [{"id": 7, "url": "https://images.igdb.com/cover.jpg"}]


def test_fetch_platforms_handles_optional_igdb_fields(client, auth_headers, monkeypatch):
    import routes.games.routes as games_routes

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, **kwargs):
            if "twitch.tv" in url:
                return FakeResponse({"access_token": "test-token"})
            assert url == "https://api.igdb.com/v4/platforms"
            assert kwargs["headers"]["Content-Type"] == "text/plain"
            return FakeResponse(
                [
                    {
                        "checksum": "checksum",
                        "created_at": 0,
                        "name": "Test Platform",
                        "updated_at": 0,
                    }
                ]
            )

    monkeypatch.setenv("IGDB_CLIENT_ID", "client-id")
    monkeypatch.setenv("IGDB_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(games_routes.httpx, "Client", lambda **kwargs: FakeClient())

    response = client.get("/games/platforms?limit=1", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()[0]["name"] == "Test Platform"
    assert response.json()[0]["platform_family"] == 0
    assert response.json()[0]["platform_logo"] == 0
    assert response.json()[0]["platform_type"] == 0


def test_achievements_and_cascade_delete(client, auth_headers):
    created_game = client.post("/games", json=GAME, headers=auth_headers).json()
    game_id = created_game["id"]
    achievement = {
        "title": "Test chamber complete",
        "description": "Finish the first chamber.",
        "points": 10,
    }

    created = client.post(
        f"/games/{game_id}/achievements",
        json=achievement,
        headers=auth_headers,
    )
    assert created.status_code == 201
    achievement_id = created.json()["achievement_id"]
    assert client.get(
        f"/games/{game_id}/achievements", headers=auth_headers
    ).json()[0]["achievement_id"] == achievement_id

    updated = client.put(
        f"/games/{game_id}/achievements/{achievement_id}",
        json={**achievement, "unlocked": True, "status": "Unlocked"},
        headers=auth_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["unlocked"] is True

    assert client.delete(
        f"/games/{game_id}/achievements/{achievement_id}", headers=auth_headers
    ).status_code == 204
    assert client.delete(f"/games/{game_id}", headers=auth_headers).status_code == 204
    assert client.get(
        f"/games/{game_id}/achievements", headers=auth_headers
    ).status_code == 404


def test_achievement_not_found_responses(client, auth_headers):
    game_id = client.post("/games", json=GAME, headers=auth_headers).json()["id"]

    assert client.put(
        f"/games/{game_id}/achievements/9999",
        json={"title": "Missing achievement"},
        headers=auth_headers,
    ).status_code == 404
    assert client.delete(
        f"/games/{game_id}/achievements/9999", headers=auth_headers
    ).status_code == 404
    assert client.delete(
        f"/games/{game_id}/achievements", headers=auth_headers
    ).status_code == 404


def test_viewer_role_can_read_but_not_write(client, auth_headers, viewer_headers):
    game_id = client.post("/games", json=GAME, headers=auth_headers).json()["id"]

    assert client.get("/games", headers=viewer_headers).status_code == 200
    assert client.get(f"/games/{game_id}", headers=viewer_headers).status_code == 200
    assert client.post("/games", json=GAME, headers=viewer_headers).status_code == 403
    assert client.put(
        f"/games/{game_id}", json=GAME, headers=viewer_headers
    ).status_code == 403
    assert client.delete(f"/games/{game_id}", headers=viewer_headers).status_code == 403
    assert client.delete("/games/all", headers=viewer_headers).status_code == 403

    achievement = {"title": "Viewer test", "description": "x", "points": 5}
    achievement_id = client.post(
        f"/games/{game_id}/achievements", json=achievement, headers=auth_headers
    ).json()["achievement_id"]

    assert client.get(
        f"/games/{game_id}/achievements", headers=viewer_headers
    ).status_code == 200
    assert client.post(
        f"/games/{game_id}/achievements", json=achievement, headers=viewer_headers
    ).status_code == 403
    assert client.put(
        f"/games/{game_id}/achievements/{achievement_id}",
        json=achievement,
        headers=viewer_headers,
    ).status_code == 403
    assert client.delete(
        f"/games/{game_id}/achievements/{achievement_id}", headers=viewer_headers
    ).status_code == 403
    assert client.delete(
        f"/games/{game_id}/achievements", headers=viewer_headers
    ).status_code == 403


def test_refresh_token_preserves_role(client, monkeypatch):
    monkeypatch.setitem(auth.AUTH_USERS, "viewer", ("viewer-pass", auth.ROLE_VIEWER))
    login = client.post(
        "/auth/token",
        data={"username": "viewer", "password": "viewer-pass"},
    )
    refreshed = client.post(
        "/auth/refresh",
        headers={"Authorization": f"Bearer {login.json()['refresh_token']}"},
    )
    assert refreshed.status_code == 200

    refreshed_headers = {
        "Authorization": f"Bearer {refreshed.json()['access_token']}"
    }
    assert client.get("/games", headers=refreshed_headers).status_code == 200
    assert client.post(
        "/games", json=GAME, headers=refreshed_headers
    ).status_code == 403


def test_not_found_and_validation_responses(client, auth_headers):
    assert client.get("/games/9999", headers=auth_headers).status_code == 404
    assert client.put(
        "/games/9999", json=GAME, headers=auth_headers
    ).status_code == 404
    assert client.delete("/games/9999", headers=auth_headers).status_code == 404
    assert client.delete("/games/all", headers=auth_headers).status_code == 204
    assert client.delete("/games/all", headers=auth_headers).status_code == 404

    invalid_game = {"title": "Incomplete game"}
    assert client.post(
        "/games", json=invalid_game, headers=auth_headers
    ).status_code == 422


def test_rate_limit_returns_retry_after_header(client, auth_headers, monkeypatch):
    import backend.auth.rate_limit as rate_limit

    middleware = app.middleware_stack.app
    assert isinstance(middleware, rate_limit.RateLimitMiddleware)
    middleware.requests.clear()
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_REQUESTS", 1)
    middleware.requests["testclient"].append(0)
    first = client.get("/games", headers=auth_headers)
    second = client.get("/games", headers=auth_headers)
    browser_error = client.get("/games", headers={"Accept": "text/html"})

    assert first.status_code == 200
    assert second.status_code == 429
    assert "Retry-After" in second.headers
    assert browser_error.status_code == 429
    assert "429" in browser_error.text
    assert "Retry-After" in browser_error.headers
    assert (
        f'data-retry-after="{browser_error.headers["Retry-After"]}"'
        in browser_error.text
    )
    assert 'role="progressbar"' in browser_error.text