import csv
import io
import json

import pytest
from fastapi.testclient import TestClient

import backend.auth.auth as auth
import backend.database.database as database
from helpers import rate_limiter
from main import app

GAME = {
    "title": "=HYPERLINK(\"https://example.com\")",
    "genre": "Puzzle",
    "platforms": "PC, PlayStation 5",
    "release_year": 2024,
    "description": "A puzzle game with multiple lines.\nSecond line.",
    "screenshots": ["https://example.com/screen.png"],
    "trailers": ["https://example.com/trailer.mp4"],
    "wishlisted": True,
    "hoursplayed": 12.5,
    "esrb": "e10",
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test.db")
    auth._login_attempts.clear()
    database.initialize_database()
    with TestClient(app) as test_client:
        rate_limiter(app).requests.clear()
        yield test_client


@pytest.fixture()
def admin_headers(client):
    response = client.post("/auth/token", data={"username": "admin", "password": "1234"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_admin_page_exposes_all_transfer_formats(client):
    response = client.get("/admin")

    assert response.status_code == 200
    for file_format in ("json", "xml", "csv", "markdown", "pdf"):
        assert f'<option value="{file_format}">' in response.text
    assert '<select name="category" id="game-category">' in response.text
    assert '<option value="Remaster">Remaster</option>' in response.text
    assert 'name="category" list=' not in response.text


@pytest.fixture()
def viewer_headers(client):
    password = "correct horse 42 battery"
    client.post("/auth/register", json={"username": "viewer", "password": password})
    response = client.post(
        "/auth/token", data={"username": "viewer", "password": password}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.parametrize("file_format", ["json", "xml", "csv", "markdown", "pdf"])
def test_exported_game_data_round_trips(client, admin_headers, file_format):
    created = client.post("/games", headers=admin_headers, json=GAME)
    assert created.status_code == 201

    exported = client.get(
        "/admin/games/export",
        headers=admin_headers,
        params={"format": file_format},
    )
    assert exported.status_code == 200
    assert exported.content

    extension = "md" if file_format == "markdown" else file_format
    imported = client.post(
        "/admin/games/import",
        headers=admin_headers,
        params={"format": file_format},
        files={"file": (f"games.{extension}", exported.content, "application/octet-stream")},
    )

    assert imported.status_code == 200, imported.text
    assert imported.json()["imported"] == 1
    games = client.get("/games?skip=0&limit=10", headers=admin_headers).json()
    copy = games[-1]
    assert copy["id"] != created.json()["id"]
    assert copy["title"] == GAME["title"]
    assert copy["platforms"] == GAME["platforms"]
    assert copy["screenshots"] == GAME["screenshots"]
    assert copy["wishlisted"] is True

    if file_format == "csv":
        csv_rows = csv.DictReader(
            io.StringIO(exported.content.decode("utf-8-sig"), newline="")
        )
        csv_title = next(csv_rows)["title"]
        assert csv_title.startswith("'="), repr(csv_title)


def test_game_data_transfer_requires_admin(client, viewer_headers):
    exported = client.get("/admin/games/export", headers=viewer_headers, params={"format": "json"})
    imported = client.post(
        "/admin/games/import",
        headers=viewer_headers,
        params={"format": "json"},
        files={"file": ("games.json", b"[]", "application/json")},
    )

    assert exported.status_code == 403
    assert imported.status_code == 403


def test_csv_round_trips_whitespace_formulas_and_null_marker(client, admin_headers):
    payload = {
        "title": " \t=HYPERLINK(https://example.com)",
        "genre": "Puzzle",
        "release_year": 2024,
        "description": r"\N",
    }
    assert client.post("/games", headers=admin_headers, json=payload).status_code == 201

    exported = client.get(
        "/admin/games/export", headers=admin_headers, params={"format": "csv"}
    )
    rows = csv.DictReader(io.StringIO(exported.content.decode("utf-8-sig"), newline=""))
    row = next(rows)
    assert row["title"].startswith("' \t=")
    assert row["description"] == r"\\N"

    imported = client.post(
        "/admin/games/import",
        headers=admin_headers,
        params={"format": "csv"},
        files={"file": ("games.csv", exported.content, "text/csv")},
    )
    assert imported.status_code == 200
    games = client.get("/games?skip=0&limit=10", headers=admin_headers).json()
    assert games[-1]["title"] == payload["title"]
    assert games[-1]["description"] == payload["description"]


def test_import_validates_all_records_before_writing(client, admin_headers):
    data = b'{"games":[{"title":"Valid","genre":"RPG","release_year":2020},' \
        b'{"title":"Invalid","genre":"RPG","release_year":"not a year"}]}'
    response = client.post(
        "/admin/games/import",
        headers=admin_headers,
        params={"format": "json"},
        files={"file": ("games.json", data, "application/json")},
    )

    assert response.status_code == 422
    assert client.get("/games?skip=0&limit=10", headers=admin_headers).json() == []


def test_json_import_normalizes_list_fields_for_database(client, admin_headers):
    data = {
        "games": [
            {
                "title": "List values",
                "genre": "Puzzle",
                "release_year": 2024,
                "platforms": ["PC", "PlayStation 5"],
                "gamemodes": ["Single Player", "Co-op"],
                "editions": ["Standard", "Deluxe"],
            }
        ]
    }
    response = client.post(
        "/admin/games/import",
        headers=admin_headers,
        params={"format": "json"},
        files={"file": ("games.json", json.dumps(data).encode(), "application/json")},
    )

    assert response.status_code == 200
    imported_game = client.get("/games?skip=0&limit=10", headers=admin_headers).json()[0]
    assert imported_game["platforms"] == "PC, PlayStation 5"
    assert imported_game["gamemodes"] == "Single Player, Co-op"
    assert imported_game["editions"] == "Standard, Deluxe"


def test_pdf_import_requires_app_attachment(client, admin_headers):
    response = client.post(
        "/admin/games/import",
        headers=admin_headers,
        params={"format": "pdf"},
        files={"file": ("external.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
    )

    assert response.status_code == 422


def test_xml_import_rejects_entity_declarations(client, admin_headers):
    data = b'<!DOCTYPE games [<!ENTITY title "Expanded">]><games><game><title>&title;</title></game></games>'
    response = client.post(
        "/admin/games/import",
        headers=admin_headers,
        params={"format": "xml"},
        files={"file": ("games.xml", data, "application/xml")},
    )

    assert response.status_code == 422
    assert client.get("/games?skip=0&limit=10", headers=admin_headers).json() == []