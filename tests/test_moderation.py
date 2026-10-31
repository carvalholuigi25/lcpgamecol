import pytest
from fastapi.testclient import TestClient

import backend.auth.auth as auth
import backend.database.database as database
from backend.moderation import rich_text
from main import app

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
def admin(client):
    return sign_in(client, "admin", "1234")


def viewer(client, monkeypatch, name):
    monkeypatch.setitem(auth.AUTH_USERS, name, (f"{name}-pass", auth.ROLE_VIEWER))
    return sign_in(client, name, f"{name}-pass")


@pytest.fixture()
def author(client, monkeypatch):
    return viewer(client, monkeypatch, "author")


@pytest.fixture()
def game_id(client, admin):
    return client.post("/games", json=GAME, headers=admin).json()["id"]


def set_rules(client, admin, **rules):
    response = client.put("/admin/moderation/settings", json=rules, headers=admin)
    assert response.status_code == 200, response.text
    return response.json()


def comment(client, headers, game_id, body="Nice game"):
    return client.post(f"/games/{game_id}/comments", json={"body": body}, headers=headers)


def comments_seen_by(client, headers, game_id):
    return client.get(f"/games/{game_id}/comments", headers=headers).json()


# --- rich text ---------------------------------------------------------------------------


def test_rich_text_keeps_editor_formatting_and_drops_the_rest():
    cleaned, text = rich_text.clean(
        '<p onclick="x">Hi <strong>there</strong><script>alert(1)</script></p>'
        '<a href="javascript:alert(1)">bad</a><a href="https://example.com">good</a><img src=x onerror=y>'
    )
    assert cleaned == (
        '<p>Hi <strong>there</strong></p><a>bad</a>'
        '<a href="https://example.com" target="_blank" rel="noopener noreferrer nofollow">good</a>'
    )
    assert text == "Hi there\nbadgood"
    assert rich_text.clean("plain a < b") == ("plain a < b", "plain a < b")


def test_posts_are_stored_clean_and_limits_count_the_text(client, author, game_id):
    # 3,457 characters of HTML, but only 900 of text: within the 1,000 character limit.
    body = "<p>" + "<strong>xxxxxx</strong>" * 150 + "</p>"
    created = comment(client, author, game_id, body)
    assert created.status_code == 201
    assert "<strong>" in created.json()["body"]
    assert comment(client, author, game_id, "<p><br></p>").status_code == 422
    too_long = {"rating": 4, "body": "<p>" + "y" * 2001 + "</p>"}
    assert client.put(f"/games/{game_id}/reviews/mine", json=too_long, headers=author).status_code == 422


# --- blocked words -----------------------------------------------------------------------


def test_settings_are_admin_only_and_normalized(client, admin, author):
    assert client.get("/admin/moderation/settings", headers=author).status_code == 403
    rules = set_rules(client, admin, blocked_words=[" Darn ", "darn", "heck it"], report_threshold=2)
    assert rules == {"blocked_words": ["darn", "heck it"], "blocked_words_action": "hold", "report_threshold": 2}


def test_blocked_words_hold_a_post_until_approved(client, admin, author, monkeypatch, game_id):
    other = viewer(client, monkeypatch, "other")
    set_rules(client, admin, blocked_words=["darn"])
    held = comment(client, author, game_id, "<p>This <em>DARN</em> level</p>").json()
    assert held["status"] == "pending"
    # "darned" is a different word.
    assert comment(client, author, game_id, "Darned good").json()["status"] == "visible"

    assert [item["id"] for item in comments_seen_by(client, other, game_id)["items"]] != [held["id"]]
    assert held["id"] in [item["id"] for item in comments_seen_by(client, author, game_id)["items"]]
    assert comments_seen_by(client, other, game_id)["count"] == 1

    queue = client.get("/admin/moderation/queue", headers=admin).json()
    assert queue["counts"]["pending"] == 1
    assert queue["items"][0]["id"] == held["id"]
    admin_titles = [item["title"] for item in client.get("/notifications", headers=admin).json()["items"]]
    assert "A comment by author waits for review" in admin_titles

    assert client.post(f"/admin/moderation/comment/{held['id']}/approve", headers=admin).status_code == 200
    assert held["id"] in [item["id"] for item in comments_seen_by(client, other, game_id)["items"]]
    assert client.get("/notifications", headers=author).json()["items"][0]["title"] == "Your comment of Celeste is visible"


def test_blocked_words_can_be_refused(client, admin, author, game_id):
    set_rules(client, admin, blocked_words=["darn"], blocked_words_action="reject")
    refused = comment(client, author, game_id, "darn")
    assert refused.status_code == 422
    assert "not allowed" in refused.json()["detail"]


# --- reports -----------------------------------------------------------------------------


def test_reports_hide_a_post_at_the_threshold(client, admin, author, monkeypatch, game_id):
    set_rules(client, admin, report_threshold=2)
    first, second = viewer(client, monkeypatch, "first"), viewer(client, monkeypatch, "second")
    posted = comment(client, author, game_id).json()
    url = f"/games/{game_id}/comments/{posted['id']}/report"

    assert client.post(url, json={"reason": "spam"}, headers=author).status_code == 400
    assert client.post(url, json={"reason": "nonsense"}, headers=first).status_code == 422
    assert client.post(url, json={"reason": "spam"}, headers=first).json() == {"reported": True, "hidden": False}
    assert client.post(url, json={"reason": "spam"}, headers=first).status_code == 409
    assert comments_seen_by(client, first, game_id)["items"][0]["reported"] is True

    result = client.post(url, json={"reason": "offensive", "details": "Rude"}, headers=second).json()
    assert result == {"reported": True, "hidden": True}
    assert comments_seen_by(client, first, game_id)["items"] == []
    assert comments_seen_by(client, admin, game_id)["items"][0]["open_reports"] == 2

    item = client.get("/admin/moderation/queue", headers=admin).json()["items"][0]
    assert (item["status"], [report["reason"] for report in item["reports"]]) == ("hidden", ["spam", "offensive"])


def test_hiding_and_removing_notify_the_author(client, admin, author, game_id):
    client.put(f"/games/{game_id}/reviews/mine", json={"rating": 2, "body": "Meh"}, headers=author)
    review = client.get(f"/games/{game_id}/reviews", headers=author).json()["mine"]

    hidden = client.post(f"/admin/moderation/review/{review['id']}/hide", json={"note": "Spoilers"}, headers=admin)
    assert hidden.json()["status"] == "hidden"
    note = client.get("/notifications", headers=author).json()["items"][0]
    assert (note["title"], note["body"]) == ("Your review of Celeste was hidden", "Spoilers")
    assert client.get(f"/games/{game_id}/reviews", headers=admin).json()["count"] == 0

    # Editing does not bring back a hidden review.
    client.put(f"/games/{game_id}/reviews/mine", json={"rating": 3, "body": "Better"}, headers=author)
    assert client.get(f"/games/{game_id}/reviews", headers=author).json()["mine"]["status"] == "hidden"

    assert client.post(f"/admin/moderation/review/{review['id']}/remove", headers=admin).status_code == 204
    assert client.get(f"/games/{game_id}/reviews", headers=author).json()["mine"] is None
    assert client.get("/notifications", headers=author).json()["items"][0]["title"] == "Your review of Celeste was removed"


def test_admin_delete_notifies_but_own_delete_does_not(client, admin, author, game_id):
    own = comment(client, author, game_id).json()
    client.delete(f"/games/{game_id}/comments/{own['id']}", headers=author)
    assert client.get("/notifications", headers=author).json()["items"] == []
    other = comment(client, author, game_id).json()
    client.delete(f"/games/{game_id}/comments/{other['id']}", headers=admin)
    assert client.get("/notifications", headers=author).json()["items"][0]["title"] == "Your comment of Celeste was removed"


def test_moderation_endpoints_are_admin_only(client, author, game_id):
    posted = comment(client, author, game_id).json()
    assert client.get("/admin/moderation/queue", headers=author).status_code == 403
    assert client.post(f"/admin/moderation/comment/{posted['id']}/hide", headers=author).status_code == 403
    assert client.get("/admin/moderation", headers=author).status_code == 200  # the page itself is static
