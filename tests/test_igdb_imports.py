import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import backend.auth.auth as auth
import backend.database.database as database
import routes.games.igdb_imports as igdb_imports
from main import app

IGDB_GAME = {
    "id": 1942,
    "name": "The Witcher 3: Wild Hunt",
    "first_release_date": 1431993600,
    "summary": "An open-world RPG.",
    "genres": [{"name": "Role-playing (RPG)"}, {"name": "Adventure"}],
    "game_modes": [{"id": 1, "name": "Single player"}],
    "platforms": [{"name": "PC (Microsoft Windows)"}, {"name": "PlayStation 4"}],
    "cover": {"url": "//images.igdb.com/igdb/image/upload/t_thumb/co1wyy.jpg"},
    "screenshots": [{"url": "//images.igdb.com/igdb/image/upload/t_thumb/sc1.jpg"}],
    "involved_companies": [{"developer": True, "publisher": True, "company": {"name": "CD Projekt RED"}}],
    "rating": 93.4,
    "aggregated_rating": 92.1,
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test.db")
    auth._login_attempts.clear()
    database.initialize_database()
    with TestClient(app) as test_client:
        app.middleware_stack.app.requests.clear()
        yield test_client


@pytest.fixture()
def igdb_calls(monkeypatch):
    calls = []

    def fake_fetch(igdb_id):
        calls.append(igdb_id)
        if igdb_id != IGDB_GAME["id"]:
            raise HTTPException(status_code=404, detail="That game was not found on IGDB")
        return IGDB_GAME

    monkeypatch.setattr(igdb_imports, "_fetch_igdb_game", fake_fetch)
    return calls


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


def test_status_requires_authentication(client):
    assert client.get("/games/igdb/1942").status_code == 401
    assert client.post("/games/igdb/1942/import").status_code == 401


def test_status_of_a_release_not_in_the_library(client, viewer_headers):
    assert client.get("/games/igdb/1942", headers=viewer_headers).json() == {
        "igdb_id": 1942,
        "game_id": None,
        "wishlisted": False,
        "favorite": False,
    }


def test_import_copies_the_igdb_game_into_the_library(client, viewer_headers, igdb_calls):
    response = client.post("/games/igdb/1942/import", headers=viewer_headers)

    assert response.status_code == 201
    game_id = response.json()["game_id"]
    game = client.get(f"/games/{game_id}", headers=viewer_headers).json()
    assert game["title"] == "The Witcher 3: Wild Hunt"
    assert game["genre"] == "Role-playing (RPG), Adventure"
    assert game["release_year"] == 2015
    assert game["release_date"] == "2015-05-19"
    assert game["gamemodes"] == "Single player"
    assert game["platforms"] == "PC (Microsoft Windows), PlayStation 4"
    assert game["cover_image_url"] == "https://images.igdb.com/igdb/image/upload/t_cover_big/co1wyy.jpg"
    assert game["developer_name"] == "CD Projekt RED"
    assert game["screenshots"] == ["https://images.igdb.com/igdb/image/upload/t_screenshot_med_2x/sc1.jpg"]


def test_import_is_idempotent(client, viewer_headers, admin_headers, igdb_calls):
    first = client.post("/games/igdb/1942/import", headers=viewer_headers).json()
    second = client.post("/games/igdb/1942/import", headers=admin_headers)

    assert second.status_code == 200
    assert second.json()["game_id"] == first["game_id"]
    assert igdb_calls == [1942]
    assert len(client.get("/games", headers=admin_headers).json()) == 1


def test_imported_release_can_be_wishlisted_and_reports_it(client, viewer_headers, igdb_calls):
    game_id = client.post("/games/igdb/1942/import", headers=viewer_headers).json()["game_id"]
    client.put(f"/games/{game_id}/wishlist", headers=viewer_headers)

    assert client.get("/games/igdb/1942", headers=viewer_headers).json() == {
        "igdb_id": 1942,
        "game_id": game_id,
        "wishlisted": True,
        "favorite": False,
    }


def test_deleting_the_library_copy_unlinks_the_release(client, viewer_headers, admin_headers, igdb_calls):
    game_id = client.post("/games/igdb/1942/import", headers=viewer_headers).json()["game_id"]

    assert client.delete(f"/games/{game_id}", headers=admin_headers).status_code == 204
    assert client.get("/games/igdb/1942", headers=viewer_headers).json()["game_id"] is None
    # It can be imported again afterwards.
    assert client.post("/games/igdb/1942/import", headers=viewer_headers).status_code == 201


def test_unknown_release_is_not_imported(client, viewer_headers, igdb_calls):
    assert client.post("/games/igdb/7/import", headers=viewer_headers).status_code == 404


def test_release_without_a_date_cannot_be_imported():
    with pytest.raises(HTTPException) as error:
        igdb_imports.game_create_from_igdb({"name": "Untitled", "first_release_date": None})
    assert error.value.status_code == 422


def test_invalid_igdb_ids_are_rejected(client, viewer_headers):
    assert client.get("/games/igdb/0", headers=viewer_headers).status_code == 422


def test_links_map_imported_releases_only(client, viewer_headers, igdb_calls):
    game_id = client.post("/games/igdb/1942/import", headers=viewer_headers).json()["game_id"]

    response = client.get("/games/igdb/links?ids=1942,7,1942", headers=viewer_headers)
    assert response.json() == {"1942": game_id}
    assert client.get("/games/igdb/links?ids=1;DROP", headers=viewer_headers).status_code == 422
    assert client.get("/games/igdb/links?ids=1942", headers={}).status_code == 401
