import pytest
from fastapi.testclient import TestClient

import backend.auth.auth as auth
import backend.database.database as database
from main import app
from routes.games.reviews import COMMENT_BODY_MAX_LENGTH, REVIEW_BODY_MAX_LENGTH

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
def other_headers(client, monkeypatch):
    monkeypatch.setitem(auth.AUTH_USERS, "other", ("other-pass", auth.ROLE_VIEWER))
    return sign_in(client, "other", "other-pass")


@pytest.fixture()
def game_id(client, admin_headers):
    return client.post("/games", json=GAME, headers=admin_headers).json()["id"]


def test_reviews_and_comments_require_authentication(client, game_id):
    assert client.get(f"/games/{game_id}/reviews").status_code == 401
    assert client.put(f"/games/{game_id}/reviews/mine", json={"rating": 5}).status_code == 401
    assert client.get(f"/games/{game_id}/comments").status_code == 401
    assert client.post(f"/games/{game_id}/comments", json={"body": "Hi"}).status_code == 401


def test_viewer_can_review_a_game_and_update_the_review(client, viewer_headers, game_id):
    empty = client.get(f"/games/{game_id}/reviews", headers=viewer_headers).json()
    assert empty == {"count": 0, "average": None, "rating_max": 5, "mine": None, "items": []}

    created = client.put(
        f"/games/{game_id}/reviews/mine", json={"rating": 4, "body": "  Tough but fair.  "}, headers=viewer_headers
    )
    assert created.status_code == 200
    review = created.json()
    assert review["username"] == "viewer"
    assert review["rating"] == 4
    assert review["body"] == "Tough but fair."

    # Saving again edits the same review instead of adding a second one.
    updated = client.put(f"/games/{game_id}/reviews/mine", json={"rating": 5, "body": ""}, headers=viewer_headers)
    assert updated.json()["id"] == review["id"]
    assert updated.json()["body"] is None

    reviews = client.get(f"/games/{game_id}/reviews", headers=viewer_headers).json()
    assert reviews["count"] == 1
    assert reviews["average"] == 5
    assert reviews["mine"]["id"] == review["id"]
    assert [item["rating"] for item in reviews["items"]] == [5]


def test_average_covers_every_review(client, viewer_headers, other_headers, game_id):
    client.put(f"/games/{game_id}/reviews/mine", json={"rating": 5}, headers=viewer_headers)
    client.put(f"/games/{game_id}/reviews/mine", json={"rating": 2}, headers=other_headers)

    reviews = client.get(f"/games/{game_id}/reviews", headers=other_headers).json()
    assert reviews["count"] == 2
    assert reviews["average"] == 3.5
    assert reviews["mine"]["username"] == "other"


def test_review_shows_the_authors_display_name(client, admin_headers, viewer_headers, game_id):
    client.put("/users/me/profile", json={"display_name": "Madeline"}, headers=viewer_headers)
    client.put(f"/games/{game_id}/reviews/mine", json={"rating": 3}, headers=viewer_headers)

    item = client.get(f"/games/{game_id}/reviews", headers=admin_headers).json()["items"][0]
    assert item["display_name"] == "Madeline"


@pytest.mark.parametrize(
    "body",
    [
        {"rating": 0},
        {"rating": 6},
        {},
        {"rating": 3, "body": "x" * (REVIEW_BODY_MAX_LENGTH + 1)},
    ],
)
def test_invalid_reviews_are_rejected(client, viewer_headers, game_id, body):
    assert client.put(f"/games/{game_id}/reviews/mine", json=body, headers=viewer_headers).status_code == 422


def test_reviewing_an_unknown_game_is_rejected(client, viewer_headers):
    assert client.get("/games/9999/reviews", headers=viewer_headers).status_code == 404
    assert client.put("/games/9999/reviews/mine", json={"rating": 3}, headers=viewer_headers).status_code == 404
    assert client.post("/games/9999/comments", json={"body": "Hi"}, headers=viewer_headers).status_code == 404


def test_only_the_author_or_an_admin_can_delete_a_review(client, admin_headers, viewer_headers, other_headers, game_id):
    review_id = client.put(f"/games/{game_id}/reviews/mine", json={"rating": 1}, headers=viewer_headers).json()["id"]
    other_id = client.put(f"/games/{game_id}/reviews/mine", json={"rating": 2}, headers=other_headers).json()["id"]

    assert client.delete(f"/games/{game_id}/reviews/{review_id}", headers=other_headers).status_code == 403
    assert client.delete(f"/games/{game_id}/reviews/{review_id}", headers=viewer_headers).status_code == 204
    assert client.delete(f"/games/{game_id}/reviews/{other_id}", headers=admin_headers).status_code == 204
    assert client.delete(f"/games/{game_id}/reviews/{other_id}", headers=admin_headers).status_code == 404
    assert client.get(f"/games/{game_id}/reviews", headers=viewer_headers).json()["count"] == 0


def test_viewers_can_comment_and_comments_are_newest_first(client, viewer_headers, other_headers, game_id):
    first = client.post(f"/games/{game_id}/comments", json={"body": " First! "}, headers=viewer_headers)
    assert first.status_code == 201
    assert first.json()["body"] == "First!"
    client.post(f"/games/{game_id}/comments", json={"body": "Second"}, headers=other_headers)
    client.post(f"/games/{game_id}/comments", json={"body": "Third"}, headers=viewer_headers)

    comments = client.get(f"/games/{game_id}/comments", headers=viewer_headers).json()
    assert comments["count"] == 3
    assert [item["body"] for item in comments["items"]] == ["Third", "Second", "First!"]
    assert [item["username"] for item in comments["items"]] == ["viewer", "other", "viewer"]

    limited = client.get(f"/games/{game_id}/comments?limit=1", headers=viewer_headers).json()
    assert limited["count"] == 3
    assert len(limited["items"]) == 1


@pytest.mark.parametrize("body", ["", "   ", "x" * (COMMENT_BODY_MAX_LENGTH + 1)])
def test_invalid_comments_are_rejected(client, viewer_headers, game_id, body):
    assert client.post(f"/games/{game_id}/comments", json={"body": body}, headers=viewer_headers).status_code == 422


def test_only_the_author_or_an_admin_can_delete_a_comment(client, admin_headers, viewer_headers, other_headers, game_id):
    comment_id = client.post(f"/games/{game_id}/comments", json={"body": "Mine"}, headers=viewer_headers).json()["id"]
    other_id = client.post(f"/games/{game_id}/comments", json={"body": "Spam"}, headers=other_headers).json()["id"]

    assert client.delete(f"/games/{game_id}/comments/{comment_id}", headers=other_headers).status_code == 403
    assert client.delete(f"/games/{game_id}/comments/{comment_id}", headers=viewer_headers).status_code == 204
    assert client.delete(f"/games/{game_id}/comments/{other_id}", headers=admin_headers).status_code == 204
    assert client.get(f"/games/{game_id}/comments", headers=viewer_headers).json()["count"] == 0


def test_deleting_a_game_removes_its_reviews_and_comments(client, admin_headers, viewer_headers, game_id):
    client.put(f"/games/{game_id}/reviews/mine", json={"rating": 4}, headers=viewer_headers)
    client.post(f"/games/{game_id}/comments", json={"body": "Nice"}, headers=viewer_headers)

    assert client.delete(f"/games/{game_id}", headers=admin_headers).status_code == 204
    with database.get_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM game_reviews").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM game_comments").fetchone()[0] == 0
