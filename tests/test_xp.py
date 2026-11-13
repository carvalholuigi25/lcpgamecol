import pytest
from fastapi.testclient import TestClient

import backend.auth.auth as auth
import backend.database.database as database
from backend.gamification import xp
from helpers import rate_limiter
from main import app

GAME = {"title": "Celeste", "genre": "Platformer", "platforms": "PC", "release_year": 2018}


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
    monkeypatch.setitem(auth.AUTH_USERS, "viewer", ("viewer-pass", auth.ROLE_VIEWER))
    return sign_in(client, "viewer", "viewer-pass")


@pytest.fixture()
def game_id(client, admin_headers):
    return client.post("/games", json=GAME, headers=admin_headers).json()["id"]


def my_xp(client, headers):
    return client.get("/users/me/xp", headers=headers).json()


# --- levels and ranks -----------------------------------------------------------------


def test_levels_grow_further_apart():
    assert [xp.xp_for_level(level) for level in (1, 2, 3, 4)] == [0, 100, 300, 600]
    assert [xp.level_for(points) for points in (0, 99, 100, 299, 300, 600)] == [1, 1, 2, 2, 3, 4]


def test_ranks_follow_levels():
    assert xp.rank_for(1) == "Rookie"
    assert xp.rank_for(4) == "Explorer"
    assert xp.rank_for(20) == "Legend"
    assert xp.rank_for(25) == "Master"
    assert xp.next_rank(4) == {"name": "Adventurer", "level": 5, "key": "adventurer"}
    assert xp.next_rank(20) == {"name": "Master", "level": 25, "key": "master"}
    assert xp.next_rank(xp.MAX_LEVEL) is None


def test_levels_stop_at_100():
    assert xp.xp_for_level(100) == 495_000
    assert xp.level_for(xp.xp_for_level(100)) == 100
    assert xp.level_for(1_000_000) == 100
    state = xp.summary(1_000_000)
    assert (state["level"], state["rank"], state["next_level_xp"], state["progress"]) == (
        100, "Apex", None, 100,
    )


def test_summary_reports_progress_through_the_level():
    assert xp.summary(150) == {
        "xp": 150, "level": 2, "rank": "Rookie", "rank_key": "rookie",
        "max_level": 100,
        "next_rank": {"name": "Explorer", "level": 3, "key": "explorer"},
        "level_xp": 100, "next_level_xp": 300, "progress": 25,
    }


# --- earning XP ------------------------------------------------------------------------


def test_xp_requires_authentication(client):
    assert client.get("/users/me/xp").status_code == 401
    assert client.get("/users/xp/leaderboard").status_code == 401


def test_daily_visit_pays_once_a_day(client, viewer_headers):
    client.get("/users", headers=viewer_headers)
    client.get("/users", headers=viewer_headers)
    state = my_xp(client, viewer_headers)
    assert state["xp"] == 10
    assert [event["action"] for event in state["recent"]] == ["daily_visit"]


def test_a_review_pays_once_per_game(client, viewer_headers, game_id):
    client.put(f"/games/{game_id}/reviews/mine", json={"rating": 4}, headers=viewer_headers)
    client.put(f"/games/{game_id}/reviews/mine", json={"rating": 5}, headers=viewer_headers)
    review_id = client.get(f"/games/{game_id}/reviews", headers=viewer_headers).json()["mine"]["id"]
    client.delete(f"/games/{game_id}/reviews/{review_id}", headers=viewer_headers)
    client.put(f"/games/{game_id}/reviews/mine", json={"rating": 3}, headers=viewer_headers)
    assert my_xp(client, viewer_headers)["xp"] == xp.ACTIONS["review"].xp


def test_wishlist_toggling_pays_once(client, viewer_headers, game_id):
    for _ in range(3):
        client.put(f"/games/{game_id}/wishlist", headers=viewer_headers)
        client.delete(f"/games/{game_id}/wishlist", headers=viewer_headers)
    client.put(f"/games/{game_id}/favorite", headers=viewer_headers)
    assert my_xp(client, viewer_headers)["xp"] == xp.ACTIONS["wishlist"].xp + xp.ACTIONS["favorite"].xp


def test_comments_have_a_daily_cap(client, viewer_headers, game_id):
    limit = xp.ACTIONS["comment"].daily_limit
    for number in range(limit + 3):
        client.post(f"/games/{game_id}/comments", json={"body": f"Comment {number}"}, headers=viewer_headers)
    assert my_xp(client, viewer_headers)["xp"] == limit * xp.ACTIONS["comment"].xp


def test_completing_the_profile_pays_once(client, viewer_headers):
    partial = {"display_name": "Vee", "bio": "Hi"}
    client.put("/users/me/profile", json=partial, headers=viewer_headers)
    assert my_xp(client, viewer_headers)["xp"] == 0
    full = {**partial, "avatar_url": "https://example.com/a.png"}
    client.put("/users/me/profile", json=full, headers=viewer_headers)
    client.put("/users/me/profile", json=full, headers=viewer_headers)
    assert my_xp(client, viewer_headers)["xp"] == xp.ACTIONS["profile"].xp


def test_reaching_a_new_level_sends_a_notification(client, viewer_headers, game_id, monkeypatch):
    monkeypatch.setitem(xp.ACTIONS, "review", xp.Action(150, "Review a game"))
    client.put(f"/games/{game_id}/reviews/mine", json={"rating": 5}, headers=viewer_headers)
    state = my_xp(client, viewer_headers)
    assert (state["level"], state["progress"]) == (2, 25)
    notification = client.get("/notifications", headers=viewer_headers).json()["items"][0]
    assert (notification["kind"], notification["title"]) == ("level_up", "You reached level 2")


def test_leaderboard_orders_by_xp(client, admin_headers, viewer_headers, game_id):
    client.put(f"/games/{game_id}/reviews/mine", json={"rating": 5}, headers=viewer_headers)
    client.put(f"/games/{game_id}/wishlist", headers=admin_headers)
    board = client.get("/users/xp/leaderboard", headers=viewer_headers).json()
    assert [(row["position"], row["username"]) for row in board] == [(1, "viewer"), (2, "admin")]
    assert board[0]["rank"] == "Rookie"


def test_badge_names_the_rank_and_its_key():
    assert xp.badge(0) == {"level": 1, "rank": "Rookie", "rank_key": "rookie"}
    assert xp.badge(xp.xp_for_level(20)) == {"level": 20, "rank": "Legend", "rank_key": "legend"}
    assert xp.badge(xp.xp_for_level(100)) == {"level": 100, "rank": "Apex", "rank_key": "apex"}


def test_describe_lists_every_rank_with_its_badge_key(client, viewer_headers):
    ranks = my_xp(client, viewer_headers)["ranks"]
    assert [rank["key"] for rank in ranks] == [name.lower() for _, name in xp.RANKS]


def test_reviews_and_comments_show_the_author_rank(client, viewer_headers, game_id, monkeypatch):
    monkeypatch.setitem(xp.ACTIONS, "review", xp.Action(300, "Review a game"))
    client.put(f"/games/{game_id}/reviews/mine", json={"rating": 5}, headers=viewer_headers)
    client.post(f"/games/{game_id}/comments", json={"body": "Nice"}, headers=viewer_headers)

    review = client.get(f"/games/{game_id}/reviews", headers=viewer_headers).json()["items"][0]
    comment = client.get(f"/games/{game_id}/comments", headers=viewer_headers).json()["items"][0]

    # 300 XP for the review, then 10 for the comment: level 3, the first Explorer level.
    assert review["author_rank"] == {"level": 3, "rank": "Explorer", "rank_key": "explorer"}
    assert comment["author_rank"] == review["author_rank"]


def test_users_directory_shows_each_rank(client, admin_headers, viewer_headers, game_id):
    client.put(f"/games/{game_id}/reviews/mine", json={"rating": 5}, headers=viewer_headers)
    users = {user["username"]: user for user in client.get("/admin/users", headers=admin_headers).json()}
    assert users["viewer"]["xp"] == xp.ACTIONS["review"].xp
    assert users["viewer"]["rank"] == {"level": 1, "rank": "Rookie", "rank_key": "rookie"}
