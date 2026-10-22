from contextlib import closing

import pytest
from fastapi.testclient import TestClient

import backend.auth.auth as auth
import backend.database.database as database
from main import app
from routes.admin.users import FAVORITE_GAMES_MAX, validate_image_url

STRONG_PASSWORD = "correct horse 42 battery"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test.db")
    auth._login_attempts.clear()
    auth._registrations.clear()
    database.initialize_database()
    with TestClient(app) as test_client:
        app.middleware_stack.app.requests.clear()
        yield test_client


@pytest.fixture()
def admin_headers(client):
    response = client.post("/auth/token", data={"username": "admin", "password": "1234"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def add_game(title, release_year=2020, cover=None):
    with closing(database.get_connection()) as connection:
        cursor = connection.execute(
            "INSERT INTO games (title, genre, release_year, platforms, cover_image_url, hoursplayed) VALUES (?, 'RPG', ?, 'PC', ?, 10)",
            (title, release_year, cover),
        )
        connection.commit()
        return cursor.lastrowid


def test_users_are_listed_with_empty_profiles(client, admin_headers):
    client.post("/auth/register", json={"username": "newplayer", "password": STRONG_PASSWORD})

    response = client.get("/admin/users", headers=admin_headers)

    assert response.status_code == 200
    listed = {user["username"]: user for user in response.json()}
    assert listed["admin"]["role"] == "admin"
    assert listed["admin"]["source"] == "configured"
    assert listed["newplayer"]["role"] == "viewer"
    assert listed["newplayer"]["source"] == "registered"
    assert listed["newplayer"]["created_at"]
    assert listed["newplayer"]["favorite_games"] == []
    assert listed["newplayer"]["avatar_url"] is None
    assert "password_hash" not in listed["newplayer"]


def test_profile_update_stores_avatar_cover_and_ordered_favorites(client, admin_headers):
    client.post("/auth/register", json={"username": "newplayer", "password": STRONG_PASSWORD})
    first = add_game("Alpha", cover="https://example.com/alpha.jpg")
    second = add_game("Beta")

    response = client.put(
        "/admin/users/NewPlayer",
        headers=admin_headers,
        json={
            "display_name": "  New Player ",
            "bio": "Loves RPGs",
            "location": "Lisbon",
            "avatar_url": "https://example.com/avatar.png",
            "cover_url": "/admin/uploads/" + "a" * 32 + "?inline=true",
            "favorite_game_ids": [second, first, second],
        },
    )

    assert response.status_code == 200
    profile = response.json()
    assert profile["username"] == "newplayer"
    assert profile["display_name"] == "New Player"
    assert profile["avatar_url"] == "https://example.com/avatar.png"
    assert [game["title"] for game in profile["favorite_games"]] == ["Beta", "Alpha"]
    assert profile["favorite_games"][1]["cover_image_url"] == "https://example.com/alpha.jpg"
    assert profile["hours_in_favorites"] == 20
    assert client.get("/admin/users/newplayer", headers=admin_headers).json() == profile


def test_configured_users_can_have_a_profile(client, admin_headers):
    response = client.put("/admin/users/admin", headers=admin_headers, json={"bio": "Runs the shelf"})

    assert response.status_code == 200
    assert response.json()["bio"] == "Runs the shelf"


def test_deleted_games_drop_out_of_favorites(client, admin_headers):
    game_id = add_game("Gone")
    client.put("/admin/users/admin", headers=admin_headers, json={"favorite_game_ids": [game_id]})

    with closing(database.get_connection()) as connection:
        connection.execute("DELETE FROM games WHERE id = ?", (game_id,))
        connection.commit()

    assert client.get("/admin/users/admin", headers=admin_headers).json()["favorite_games"] == []


def test_profile_update_rejects_unknown_games_and_too_many_favorites(client, admin_headers):
    unknown = client.put("/admin/users/admin", headers=admin_headers, json={"favorite_game_ids": [999]})
    too_many = client.put(
        "/admin/users/admin",
        headers=admin_headers,
        json={"favorite_game_ids": list(range(1, FAVORITE_GAMES_MAX + 2))},
    )

    assert unknown.status_code == 400
    assert too_many.status_code == 422


@pytest.mark.parametrize(
    "url",
    ["javascript:alert(1)", "data:image/png;base64,AAAA", "//evil.example/x.png", "/public/../main.py", "/admin/uploads/abc"],
)
def test_unsafe_image_links_are_rejected(client, admin_headers, url):
    response = client.put("/admin/users/admin", headers=admin_headers, json={"avatar_url": url})

    assert response.status_code == 422


def test_image_link_validation_allows_safe_sources():
    assert validate_image_url("") is None
    assert validate_image_url(" https://example.com/a.png ") == "https://example.com/a.png"
    assert validate_image_url("/public/images/default-game-cover.svg") == "/public/images/default-game-cover.svg"


def test_unknown_users_return_404(client, admin_headers):
    assert client.get("/admin/users/nobody", headers=admin_headers).status_code == 404
    assert client.put("/admin/users/nobody", headers=admin_headers, json={}).status_code == 404


def test_game_options_list_every_game(client, admin_headers):
    add_game("Zeta")
    add_game("alpha")

    response = client.get("/admin/users/game-options", headers=admin_headers)

    assert [game["title"] for game in response.json()] == ["alpha", "Zeta"]


def test_users_directory_requires_admin(client):
    client.post("/auth/register", json={"username": "newplayer", "password": STRONG_PASSWORD})
    token = client.post(
        "/auth/token", data={"username": "newplayer", "password": STRONG_PASSWORD}
    ).json()["access_token"]
    viewer_headers = {"Authorization": f"Bearer {token}"}
    client.cookies.clear()

    assert client.get("/admin/users").status_code == 401
    assert client.get("/admin/users", headers=viewer_headers).status_code == 403
    assert client.put("/admin/users/newplayer", headers=viewer_headers, json={}).status_code == 403


def test_users_page_is_served(client):
    response = client.get("/admin/user-directory")

    assert response.status_code == 200
    assert "Favorite games" in response.text
