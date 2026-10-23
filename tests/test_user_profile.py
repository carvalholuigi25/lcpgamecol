from contextlib import closing

import pytest
from fastapi.testclient import TestClient

import backend.auth.auth as auth
import backend.database.database as database
from main import app
from routes.admin.users import FAVORITE_GAMES_MAX

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


def sign_in(client, username, password):
    token = client.post("/auth/token", data={"username": username, "password": password}).json()["access_token"]
    client.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def viewer_headers(client):
    client.post("/auth/register", json={"username": "newplayer", "password": STRONG_PASSWORD})
    return sign_in(client, "newplayer", STRONG_PASSWORD)


def add_game(title):
    with closing(database.get_connection()) as connection:
        cursor = connection.execute(
            "INSERT INTO games (title, genre, release_year, platforms, hoursplayed) VALUES (?, 'RPG', 2020, 'PC', 5)",
            (title,),
        )
        connection.commit()
        return cursor.lastrowid


def test_own_profile_starts_empty(client, viewer_headers):
    response = client.get("/users/me/profile", headers=viewer_headers)

    assert response.status_code == 200
    profile = response.json()
    assert profile["username"] == "newplayer"
    assert profile["role"] == "viewer"
    assert profile["display_name"] is None
    assert profile["favorite_games"] == []
    assert profile["wishlist_games"] == []
    assert profile["favorites_max"] == FAVORITE_GAMES_MAX


def test_viewers_can_edit_their_own_profile(client, viewer_headers):
    response = client.put(
        "/users/me/profile",
        headers=viewer_headers,
        json={"display_name": " Player One ", "bio": "Hello", "avatar_url": "https://example.com/a.png"},
    )

    assert response.status_code == 200
    assert response.json()["display_name"] == "Player One"
    assert client.get("/users/me/profile", headers=viewer_headers).json()["avatar_url"] == "https://example.com/a.png"


def test_saving_without_favorites_keeps_them(client, viewer_headers):
    game_id = add_game("Alpha")
    client.put(f"/games/{game_id}/favorite", headers=viewer_headers)

    response = client.put("/users/me/profile", headers=viewer_headers, json={"bio": "Still here"})

    assert [game["id"] for game in response.json()["favorite_games"]] == [game_id]


def test_favorites_can_be_reordered_and_removed(client, viewer_headers):
    first, second, third = add_game("Alpha"), add_game("Beta"), add_game("Gamma")
    for game_id in (first, second, third):
        client.put(f"/games/{game_id}/favorite", headers=viewer_headers)

    reordered = client.put("/users/me/profile", headers=viewer_headers, json={"favorite_game_ids": [third, first]})

    assert reordered.status_code == 200
    assert [game["title"] for game in reordered.json()["favorite_games"]] == ["Gamma", "Alpha"]
    assert client.get("/users/me/game-lists", headers=viewer_headers).json()["favorites"] == [third, first]


def test_own_profile_lists_wishlist_games(client, viewer_headers):
    game_id = add_game("Wanted")
    client.put(f"/games/{game_id}/wishlist", headers=viewer_headers)

    wishlist = client.get("/users/me/profile", headers=viewer_headers).json()["wishlist_games"]

    assert [game["title"] for game in wishlist] == ["Wanted"]
    assert wishlist[0]["hours_played"] == 5


def test_own_profile_rejects_unsafe_links_and_unknown_games(client, viewer_headers):
    unsafe = client.put("/users/me/profile", headers=viewer_headers, json={"cover_url": "javascript:alert(1)"})
    unknown = client.put("/users/me/profile", headers=viewer_headers, json={"favorite_game_ids": [999]})

    assert unsafe.status_code == 422
    assert unknown.status_code == 400


def test_own_profile_is_shared_with_the_user_directory(client, viewer_headers):
    client.put("/users/me/profile", headers=viewer_headers, json={"location": "Porto"})
    admin_headers = sign_in(client, "admin", "1234")

    assert client.get("/admin/users/newplayer", headers=admin_headers).json()["location"] == "Porto"


def test_own_profile_requires_sign_in(client):
    client.cookies.clear()

    assert client.get("/users/me/profile").status_code == 401
    assert client.put("/users/me/profile", json={}).status_code == 401


def test_profile_page_is_served(client):
    response = client.get("/profile")

    assert response.status_code == 200
    assert "My profile" in response.text
