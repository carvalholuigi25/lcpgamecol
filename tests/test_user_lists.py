import pytest
from fastapi.testclient import TestClient

import backend.auth.auth as auth
import backend.database.database as database
from main import app
from routes.admin.users import FAVORITE_GAMES_MAX

GAME = {"title": "Celeste", "genre": "Platformer", "platforms": "PC", "release_year": 2018}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test.db")
    auth._login_attempts.clear()
    database.initialize_database()
    with TestClient(app) as test_client:
        app.middleware_stack.app.requests.clear()
        yield test_client


def sign_in(client, username, password):
    response = client.post("/auth/token", data={"username": username, "password": password})
    assert response.status_code == 200
    client.cookies.clear()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture()
def admin_headers(client):
    return sign_in(client, "admin", "1234")


@pytest.fixture()
def viewer_headers(client, monkeypatch):
    monkeypatch.setitem(auth.AUTH_USERS, "viewer", ("viewer-pass", auth.ROLE_VIEWER))
    return sign_in(client, "viewer", "viewer-pass")


@pytest.fixture()
def game_id(client, admin_headers):
    return client.post("/games", json=GAME, headers=admin_headers).json()["id"]


def test_lists_require_authentication(client, game_id):
    assert client.get("/users/me/game-lists").status_code == 401
    assert client.put(f"/games/{game_id}/wishlist").status_code == 401
    assert client.put(f"/games/{game_id}/favorite").status_code == 401


def test_viewer_can_wishlist_and_favorite_a_game(client, viewer_headers, game_id):
    assert client.get("/users/me/game-lists", headers=viewer_headers).json() == {
        "wishlist": [],
        "favorites": [],
        "favorites_max": FAVORITE_GAMES_MAX,
    }

    wishlisted = client.put(f"/games/{game_id}/wishlist", headers=viewer_headers)
    assert wishlisted.json() == {"game_id": game_id, "wishlisted": True, "favorite": False}
    # Adding twice is harmless.
    assert client.put(f"/games/{game_id}/wishlist", headers=viewer_headers).status_code == 200

    favorite = client.put(f"/games/{game_id}/favorite", headers=viewer_headers)
    assert favorite.json() == {"game_id": game_id, "wishlisted": True, "favorite": True}

    lists = client.get("/users/me/game-lists", headers=viewer_headers).json()
    assert lists["wishlist"] == [game_id]
    assert lists["favorites"] == [game_id]

    removed = client.delete(f"/games/{game_id}/wishlist", headers=viewer_headers)
    assert removed.json() == {"game_id": game_id, "wishlisted": False, "favorite": True}
    unfavorited = client.delete(f"/games/{game_id}/favorite", headers=viewer_headers)
    assert unfavorited.json() == {"game_id": game_id, "wishlisted": False, "favorite": False}


def test_lists_are_kept_per_user(client, admin_headers, viewer_headers, game_id):
    client.put(f"/games/{game_id}/wishlist", headers=viewer_headers)

    assert client.get("/users/me/game-lists", headers=admin_headers).json()["wishlist"] == []


def test_library_favorites_appear_in_the_user_directory(client, admin_headers, viewer_headers, game_id):
    client.put(f"/games/{game_id}/favorite", headers=viewer_headers)

    profile = client.get("/admin/users/viewer", headers=admin_headers).json()
    assert [game["id"] for game in profile["favorite_games"]] == [game_id]


def test_unknown_game_is_rejected(client, viewer_headers):
    assert client.put("/games/9999/wishlist", headers=viewer_headers).status_code == 404
    assert client.delete("/games/9999/favorite", headers=viewer_headers).status_code == 404


def test_favorites_are_capped(client, admin_headers, viewer_headers):
    ids = [
        client.post("/games", json={**GAME, "title": f"Game {index}"}, headers=admin_headers).json()["id"]
        for index in range(FAVORITE_GAMES_MAX + 1)
    ]
    for game_id in ids[:-1]:
        assert client.put(f"/games/{game_id}/favorite", headers=viewer_headers).status_code == 200

    response = client.put(f"/games/{ids[-1]}/favorite", headers=viewer_headers)
    assert response.status_code == 409
    # Re-adding one that is already a favorite is not blocked by the cap.
    assert client.put(f"/games/{ids[0]}/favorite", headers=viewer_headers).status_code == 200


def test_deleting_a_game_removes_it_from_lists(client, admin_headers, viewer_headers, game_id):
    client.put(f"/games/{game_id}/wishlist", headers=viewer_headers)
    client.put(f"/games/{game_id}/favorite", headers=viewer_headers)

    assert client.delete(f"/games/{game_id}", headers=admin_headers).status_code == 204
    assert client.get("/users/me/game-lists", headers=viewer_headers).json()["wishlist"] == []
    assert client.get("/users/me/game-lists", headers=viewer_headers).json()["favorites"] == []


def test_viewers_still_cannot_edit_or_delete_games(client, viewer_headers, game_id):
    assert client.put(f"/games/{game_id}", json=GAME, headers=viewer_headers).status_code == 403
    assert client.delete(f"/games/{game_id}", headers=viewer_headers).status_code == 403
