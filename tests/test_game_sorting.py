import pytest
from fastapi.testclient import TestClient

import backend.auth.auth as auth
import backend.database.database as database
import routes.games.routes as games_routes
from main import app
from routes.games.schemas import ReleaseSort, SortOrder

GAMES = [
    {"title": "beta", "genre": "A", "platforms": "PC", "release_year": 2015, "release_date": "2015-06-01",
     "user_rating": 80, "critic_rating": 0, "hoursplayed": 5},
    {"title": "Alpha", "genre": "A", "platforms": "PC", "release_year": 2020, "release_date": None,
     "user_rating": 95, "critic_rating": 70, "hoursplayed": 40},
    {"title": "Gamma", "genre": "A", "platforms": "PC", "release_year": 2018, "release_date": "2018-03-10",
     "user_rating": None, "critic_rating": 90, "hoursplayed": 12},
]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test.db")
    auth._login_attempts.clear()
    database.initialize_database()
    with TestClient(app) as test_client:
        app.middleware_stack.app.requests.clear()
        token = test_client.post("/auth/token", data={"username": "admin", "password": "1234"}).json()["access_token"]
        test_client.cookies.clear()
        test_client.headers["Authorization"] = f"Bearer {token}"
        for game in GAMES:
            assert test_client.post("/games", json=game).status_code == 201
        yield test_client


def titles(client, path="/games/page", **params):
    response = client.get(path, params=params)
    assert response.status_code == 200, response.text
    body = response.json()
    return [game["title"] for game in (body["items"] if isinstance(body, dict) else body)]


def test_default_order_is_unchanged(client):
    assert titles(client) == ["beta", "Alpha", "Gamma"]


@pytest.mark.parametrize(
    "params, expected",
    [
        ({"sort": "added", "order": "desc"}, ["Gamma", "Alpha", "beta"]),
        ({"sort": "title"}, ["Alpha", "beta", "Gamma"]),  # case-insensitive
        ({"sort": "title", "order": "desc"}, ["Gamma", "beta", "Alpha"]),
        # Newest first by default; "Alpha" has only a year, which still sorts correctly.
        ({"sort": "release_date"}, ["Alpha", "Gamma", "beta"]),
        ({"sort": "release_date", "order": "asc"}, ["beta", "Gamma", "Alpha"]),
        ({"sort": "user_rating"}, ["Alpha", "beta", "Gamma"]),
        ({"sort": "critic_rating"}, ["Gamma", "Alpha", "beta"]),
        ({"sort": "hours_played"}, ["Alpha", "Gamma", "beta"]),
        ({"sort": "hours_played", "order": "asc"}, ["beta", "Gamma", "Alpha"]),
    ],
)
def test_library_sorts(client, params, expected):
    assert titles(client, **params) == expected


def test_unrated_games_stay_last_in_both_directions(client):
    assert titles(client, sort="user_rating", order="desc")[-1] == "Gamma"
    assert titles(client, sort="user_rating", order="asc")[-1] == "Gamma"


def test_sorting_applies_before_pagination(client):
    first = titles(client, sort="title", limit=2)
    second = titles(client, sort="title", limit=2, skip=2)
    assert first + second == ["Alpha", "beta", "Gamma"]


def test_list_and_search_endpoints_sort_too(client):
    assert titles(client, "/games", sort="title") == ["Alpha", "beta", "Gamma"]
    assert titles(client, "/games/search", genre="A", sort="critic_rating") == ["Gamma", "Alpha", "beta"]


@pytest.mark.parametrize("params", [{"sort": "id; DROP TABLE games"}, {"sort": "title", "order": "sideways"}])
def test_unknown_sort_values_are_rejected(client, params):
    assert client.get("/games/page", params=params).status_code == 422


@pytest.mark.parametrize(
    "sort, order, expected",
    [
        (ReleaseSort.RELEASE_DATE, None, "sort first_release_date asc; "),
        (ReleaseSort.RELEASE_DATE, SortOrder.DESC, "sort first_release_date desc; "),
        (ReleaseSort.TITLE, None, "sort name asc; "),
        (ReleaseSort.HYPE, None, "sort hypes desc; "),
        (ReleaseSort.USER_RATING, None, "sort rating desc; "),
        (ReleaseSort.CRITIC_RATING, SortOrder.ASC, "sort aggregated_rating asc; "),
    ],
)
def test_release_sort_clause(sort, order, expected):
    assert games_routes.release_sort_clause(sort, order) == expected


def test_release_route_passes_sort_to_igdb(client, monkeypatch):
    calls = []

    def fake_fetch(*args):
        calls.append(args)
        return games_routes.GameReleasePage(items=[], total=0, page_size=5)

    monkeypatch.setattr(games_routes, "_fetch_all_games_by_date", fake_fetch)
    response = client.get("/games/all-releases", params={"year": 2026, "month": 1, "day": 1, "limit": 5, "sort": "hype"})

    assert response.status_code == 200
    assert calls == [(2026, 1, 1, 5, 0, ReleaseSort.HYPE, None)]
    assert client.get("/games/all-releases", params={"sort": "hours_played"}).status_code == 422
