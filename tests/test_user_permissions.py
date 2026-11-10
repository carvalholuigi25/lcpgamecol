import pytest
from fastapi.testclient import TestClient

import backend.auth.auth as auth
import backend.database.database as database
from helpers import rate_limiter
from main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test.db")
    auth._login_attempts.clear()
    database.initialize_database()
    with TestClient(app) as test_client:
        rate_limiter(app).requests.clear()
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
    monkeypatch.setitem(auth.AUTH_USERS, "permission-viewer", ("viewer-pass", auth.ROLE_VIEWER))
    return sign_in(client, "permission-viewer", "viewer-pass")


def test_permissions_page_and_api_are_admin_only(client, viewer_headers):
    assert client.get("/admin/permissions", headers=viewer_headers).status_code == 403
    assert client.get("/pages/admin/permissions.html", headers=viewer_headers).status_code == 403
    assert client.get("/admin/permissions").status_code == 401
    assert client.get("/admin/permissions/api", headers=viewer_headers).status_code == 403


def test_admin_can_grant_and_revoke_game_permissions(client, admin_headers, viewer_headers):
    response = client.get("/admin/permissions/api", headers=admin_headers)
    assert response.status_code == 200
    assert any(item["key"] == "games.create" for item in response.json()["permissions"])

    denied = client.post("/games", json={"title": "Game", "genre": "Puzzle", "platforms": "PC", "release_year": 2025},
                         headers=viewer_headers)
    assert denied.status_code == 403

    saved = client.put(
        "/admin/permissions/api/permission-viewer",
        json={"permissions": ["games.create"]},
        headers=admin_headers,
    )
    assert saved.status_code == 200
    created = client.post(
        "/games",
        json={"title": "Granted Game", "genre": "Puzzle", "platforms": "PC", "release_year": 2025},
        headers=viewer_headers,
    )
    assert created.status_code == 201
    game_id = created.json()["id"]
    assert client.put(
        f"/games/{game_id}",
        json={"title": "Changed", "genre": "Puzzle", "platforms": "PC", "release_year": 2025},
        headers=viewer_headers,
    ).status_code == 403
    assert client.delete(f"/games/{game_id}", headers=viewer_headers).status_code == 403

    assert client.put(
        "/admin/permissions/api/permission-viewer",
        json={"permissions": ["games.edit"]},
        headers=admin_headers,
    ).status_code == 200
    updated = client.put(
        f"/games/{game_id}",
        json={"title": "Changed", "genre": "Puzzle", "platforms": "PC", "release_year": 2025},
        headers=viewer_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Changed"

    assert client.put(
        "/admin/permissions/api/permission-viewer",
        json={"permissions": []},
        headers=admin_headers,
    ).status_code == 200
    denied_again = client.post(
        "/games",
        json={"title": "No Longer Granted", "genre": "Puzzle", "platforms": "PC", "release_year": 2025},
        headers=viewer_headers,
    )
    assert denied_again.status_code == 403

    assert client.put(
        "/admin/permissions/api/permission-viewer",
        json={"permissions": ["games.delete"]},
        headers=admin_headers,
    ).status_code == 200
    assert client.delete(f"/games/{game_id}", headers=viewer_headers).status_code == 204


def test_user_profile_permission_and_invalid_grants(client, admin_headers, viewer_headers):
    assert client.put(
        "/admin/users/admin",
        json={"display_name": "Updated by viewer"},
        headers=viewer_headers,
    ).status_code == 403
    assert client.put(
        "/admin/permissions/api/permission-viewer",
        json={"permissions": ["users.edit_profile"]},
        headers=admin_headers,
    ).status_code == 200
    assert client.put(
        "/admin/users/admin",
        json={"display_name": "Updated by viewer"},
        headers=viewer_headers,
    ).status_code == 200

    invalid = client.put(
        "/admin/permissions/api/permission-viewer",
        json={"permissions": ["users.manage_everything"]},
        headers=admin_headers,
    )
    assert invalid.status_code == 422


def test_readonly_grants_have_a_scoped_management_workspace(client, admin_headers, viewer_headers):
    assert client.get("/users/me/permissions", headers=viewer_headers).json() == {
        "username": "permission-viewer",
        "role": "viewer",
        "permissions": [],
    }
    assert client.get("/workspace", headers=viewer_headers).status_code == 200
    assert client.get("/admin/dashboard", headers=viewer_headers).status_code == 403
    assert client.get("/users/manageable", headers=viewer_headers).status_code == 403

    created = client.post(
        "/games",
        json={"title": "Favorite", "genre": "Puzzle", "platforms": "PC", "release_year": 2024},
        headers=admin_headers,
    )
    assert created.status_code == 201
    game_id = created.json()["id"]
    second_game = client.post(
        "/games",
        json={"title": "Another Favorite", "genre": "Action", "platforms": "PC", "release_year": 2025},
        headers=admin_headers,
    )
    assert second_game.status_code == 201
    second_game_id = second_game.json()["id"]
    assert client.put(
        "/admin/users/admin",
        json={"display_name": "Before", "favorite_game_ids": [game_id], "email": "admin@example.com"},
        headers=admin_headers,
    ).status_code == 200
    assert client.put(
        "/admin/permissions/api/permission-viewer",
        json={"permissions": ["users.edit_profile"]},
        headers=admin_headers,
    ).status_code == 200

    capabilities = client.get("/users/me/permissions", headers=viewer_headers)
    assert capabilities.status_code == 200
    assert capabilities.json()["permissions"] == ["users.edit_profile"]
    users = client.get("/users/manageable", headers=viewer_headers)
    assert users.status_code == 200
    assert {user["username"] for user in users.json()} >= {"admin", "permission-viewer"}
    profile = client.get("/users/manageable/admin", headers=viewer_headers)
    assert profile.status_code == 200
    assert "email" not in profile.json()
    assert "favorite_games" not in profile.json()
    updated = client.put(
        "/users/manageable/admin",
        json={"display_name": "Updated by grantee", "favorite_game_ids": [second_game_id]},
        headers=viewer_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["display_name"] == "Updated by grantee"
    preserved = client.put(
        "/users/manageable/admin",
        json={"location": "Updated without changing favorites"},
        headers=viewer_headers,
    )
    assert preserved.status_code == 200

    admin_profile = client.get("/admin/users/admin", headers=admin_headers).json()
    assert admin_profile["email"] == "admin@example.com"
    assert [game["id"] for game in admin_profile["favorite_games"]] == [second_game_id]
    invalid_favorite = client.put(
        "/users/manageable/admin",
        json={"favorite_game_ids": [999999]},
        headers=viewer_headers,
    )
    assert invalid_favorite.status_code == 400
