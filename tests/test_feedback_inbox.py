from contextlib import closing
from email import message_from_bytes, policy

import pytest
from fastapi.testclient import TestClient

import backend.auth.auth as auth
import backend.database.database as database
from backend.mail import mailer
from main import app

STRONG_PASSWORD = "correct horse 42 battery"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(mailer, "SMTP_HOST", "")
    monkeypatch.setattr(mailer, "MAIL_OUTBOX_DIR", "")
    monkeypatch.setitem(auth.AUTH_USERS, "boss", ("boss-pass", auth.ROLE_ADMIN))
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
def admin_headers(client):
    return sign_in(client, "boss", "boss-pass")


@pytest.fixture()
def viewer_headers(client):
    client.post("/auth/register", json={"username": "newplayer", "password": STRONG_PASSWORD})
    return sign_in(client, "newplayer", STRONG_PASSWORD)


@pytest.fixture()
def outbox(tmp_path, monkeypatch):
    folder = tmp_path / "outbox"
    monkeypatch.setattr(mailer, "MAIL_OUTBOX_DIR", str(folder))
    return folder


def outbox_messages(folder):
    return [message_from_bytes(path.read_bytes(), policy=policy.default) for path in sorted(folder.glob("*.eml"))]


def set_email(client, headers, email):
    response = client.put("/users/me/profile", json={"email": email}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# --- profile email -------------------------------------------------------------


def test_profile_email_is_validated_and_kept_when_left_out(client, viewer_headers, admin_headers):
    assert client.put("/users/me/profile", json={"email": "not-an-email"}, headers=viewer_headers).status_code == 422
    assert set_email(client, viewer_headers, " player@example.com ")["email"] == "player@example.com"

    # The user directory form doesn't send an email, which must not erase it.
    response = client.put("/admin/users/newplayer", json={"bio": "Hi"}, headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["email"] == "player@example.com"

    assert set_email(client, viewer_headers, "")["email"] is None


# --- feedback ------------------------------------------------------------------


def test_feedback_requires_sign_in(client):
    assert client.post("/feedback", json={"subject": "Hi", "message": "Hello"}).status_code == 401
    assert client.get("/feedback/mine").status_code == 401


def test_users_send_and_list_their_own_feedback(client, viewer_headers, admin_headers):
    response = client.post(
        "/feedback",
        json={"category": "bug", "subject": "  Broken \n cover ", "message": " It is blank ", "page_url": "/library"},
        headers=viewer_headers,
    )
    assert response.status_code == 201
    item = response.json()
    assert item["subject"] == "Broken cover"
    assert item["message"] == "It is blank"
    assert item["status"] == "open"
    assert "email_status" not in item

    client.post("/feedback", json={"subject": "Mine", "message": "Admin note"}, headers=admin_headers)
    mine = client.get("/feedback/mine", headers=viewer_headers).json()
    assert [entry["subject"] for entry in mine] == ["Broken cover"]


@pytest.mark.parametrize("page_url", ["https://evil.example", "//evil.example", "library", "/a\\b"])
def test_feedback_page_must_be_an_app_path(client, viewer_headers, page_url):
    response = client.post(
        "/feedback", json={"subject": "Hi", "message": "Hello", "page_url": page_url}, headers=viewer_headers
    )
    assert response.status_code == 422


def test_feedback_rejects_unknown_categories_and_blank_text(client, viewer_headers):
    for body in (
        {"category": "spam", "subject": "Hi", "message": "Hello"},
        {"subject": "   ", "message": "Hello"},
        {"subject": "Hi", "message": "   "},
    ):
        assert client.post("/feedback", json=body, headers=viewer_headers).status_code == 422


def test_new_feedback_notifies_administrators(client, viewer_headers, admin_headers):
    client.post("/feedback", json={"subject": "Idea", "message": "Dark mode"}, headers=viewer_headers)

    notifications = client.get("/notifications", headers=admin_headers).json()
    assert notifications["unread"] == 1
    assert notifications["items"][0]["kind"] == "feedback_new"
    assert notifications["items"][0]["link"] == "/feedback#manage"
    assert client.get("/notifications", headers=viewer_headers).json()["unread"] == 0


def test_only_administrators_manage_feedback(client, viewer_headers):
    feedback_id = client.post("/feedback", json={"subject": "Hi", "message": "Hello"}, headers=viewer_headers).json()["id"]

    assert client.get("/admin/feedback", headers=viewer_headers).status_code == 403
    assert client.put(f"/admin/feedback/{feedback_id}", json={"status": "closed"}, headers=viewer_headers).status_code == 403
    assert client.delete(f"/admin/feedback/{feedback_id}", headers=viewer_headers).status_code == 403


def test_admin_reply_notifies_and_emails_the_user(client, viewer_headers, admin_headers, outbox):
    set_email(client, viewer_headers, "player@example.com")
    feedback_id = client.post("/feedback", json={"subject": "Crash", "message": "On save"}, headers=viewer_headers).json()["id"]

    response = client.put(f"/admin/feedback/{feedback_id}", json={"reply": "Fixed, thanks!"}, headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "answered"
    assert response.json()["replied_by"] == "boss"

    listing = client.get("/admin/feedback", headers=admin_headers).json()
    assert listing["items"][0]["email_status"] == mailer.STATUS_SAVED
    assert listing["counts"]["answered"] == 1
    assert listing["email_enabled"] is True

    emails = outbox_messages(outbox)
    assert len(emails) == 1
    assert emails[0]["To"] == "player@example.com"
    assert emails[0]["Subject"] == "Re: Crash"
    assert "Fixed, thanks!" in emails[0].get_content()

    notifications = client.get("/notifications", headers=viewer_headers).json()
    assert notifications["items"][0]["kind"] == "feedback_reply"
    assert client.get("/feedback/mine", headers=viewer_headers).json()[0]["reply"] == "Fixed, thanks!"


def test_reply_without_an_address_records_why_no_email_went_out(client, viewer_headers, admin_headers, outbox):
    feedback_id = client.post("/feedback", json={"subject": "Hi", "message": "Hello"}, headers=viewer_headers).json()["id"]
    client.put(f"/admin/feedback/{feedback_id}", json={"reply": "Hello back"}, headers=admin_headers)

    item = client.get("/admin/feedback", headers=admin_headers).json()["items"][0]
    assert item["email_status"] == mailer.STATUS_NO_ADDRESS
    assert not outbox.exists()


def test_status_change_notifies_without_email(client, viewer_headers, admin_headers, outbox):
    set_email(client, viewer_headers, "player@example.com")
    feedback_id = client.post("/feedback", json={"subject": "Hi", "message": "Hello"}, headers=viewer_headers).json()["id"]

    response = client.put(f"/admin/feedback/{feedback_id}", json={"status": "in_progress"}, headers=admin_headers)
    assert response.json()["status"] == "in_progress"
    assert client.get("/notifications", headers=viewer_headers).json()["items"][0]["title"] == "Your feedback is now in progress"
    assert not outbox.exists()

    filtered = client.get("/admin/feedback?status=in_progress", headers=admin_headers).json()["items"]
    assert [item["id"] for item in filtered] == [feedback_id]


def test_admin_can_delete_feedback(client, viewer_headers, admin_headers):
    feedback_id = client.post("/feedback", json={"subject": "Hi", "message": "Hello"}, headers=viewer_headers).json()["id"]
    assert client.delete(f"/admin/feedback/{feedback_id}", headers=admin_headers).status_code == 204
    assert client.delete(f"/admin/feedback/{feedback_id}", headers=admin_headers).status_code == 404
    assert client.get("/feedback/mine", headers=viewer_headers).json() == []


# --- notifications -------------------------------------------------------------


def test_notifications_can_be_read_and_deleted_by_their_owner_only(client, viewer_headers, admin_headers):
    for subject in ("One", "Two"):
        client.post("/feedback", json={"subject": subject, "message": "Hello"}, headers=viewer_headers)
    items = client.get("/notifications", headers=admin_headers).json()["items"]
    first, second = items[0]["id"], items[1]["id"]

    assert client.post(f"/notifications/{first}/read", headers=viewer_headers).status_code == 404
    assert client.delete(f"/notifications/{first}", headers=viewer_headers).status_code == 404

    assert client.post(f"/notifications/{first}/read", headers=admin_headers).json() == {"unread": 1}
    assert client.delete(f"/notifications/{second}", headers=admin_headers).status_code == 204
    listing = client.get("/notifications", headers=admin_headers).json()
    assert listing["unread"] == 0
    assert [item["id"] for item in listing["items"]] == [first]


def test_mark_all_notifications_read(client, viewer_headers, admin_headers):
    for subject in ("One", "Two", "Three"):
        client.post("/feedback", json={"subject": subject, "message": "Hello"}, headers=viewer_headers)
    assert client.post("/notifications/read-all", headers=admin_headers).json() == {"unread": 0}
    assert all(item["read"] for item in client.get("/notifications", headers=admin_headers).json()["items"])


def test_old_notifications_are_trimmed(client, monkeypatch, viewer_headers):
    from routes.users import notifications

    monkeypatch.setattr(notifications, "NOTIFICATIONS_KEPT_PER_USER", 3)
    for index in range(5):
        notifications.notify("newplayer", "system", f"Note {index}")
    titles = [item["title"] for item in client.get("/notifications", headers=viewer_headers).json()["items"]]
    assert titles == ["Note 4", "Note 3", "Note 2"]


# --- messages ------------------------------------------------------------------


def test_recipients_list_every_other_account(client, viewer_headers):
    usernames = [item["username"] for item in client.get("/messages/recipients", headers=viewer_headers).json()]
    assert "boss" in usernames
    assert "newplayer" not in usernames


def test_send_read_and_reply_to_a_message(client, viewer_headers, admin_headers, outbox):
    set_email(client, admin_headers, "boss@example.com")
    response = client.post(
        "/messages", json={"recipient": "BOSS", "subject": "Hello", "body": "Can you add Hades?"}, headers=viewer_headers
    )
    assert response.status_code == 201
    sent = response.json()
    assert sent["recipient"] == "boss"
    assert sent["incoming"] is False

    inbox = client.get("/messages", headers=admin_headers).json()
    assert inbox["unread"] == 1
    assert inbox["items"][0]["body"] == "Can you add Hades?"
    assert inbox["items"][0]["incoming"] is True
    assert client.get("/notifications", headers=admin_headers).json()["items"][0]["kind"] == "message"
    assert client.get("/messages?box=sent", headers=viewer_headers).json()["items"][0]["id"] == sent["id"]

    emails = outbox_messages(outbox)
    assert emails[0]["To"] == "boss@example.com"
    assert emails[0]["Subject"] == "New message from newplayer: Hello"

    assert client.post(f"/messages/{sent['id']}/read", headers=admin_headers).json() == {"unread": 0}
    reply = client.post(
        "/messages", json={"recipient": "newplayer", "subject": "Re: Hello", "body": "Done", "reply_to": sent["id"]},
        headers=admin_headers,
    )
    assert reply.status_code == 201
    assert reply.json()["reply_to"] == sent["id"]
    assert client.get("/messages", headers=viewer_headers).json()["unread"] == 1


def test_messages_reject_unknown_recipients_and_blank_bodies(client, viewer_headers):
    body = {"subject": "Hi", "body": "Hello"}
    assert client.post("/messages", json={**body, "recipient": "ghost"}, headers=viewer_headers).status_code == 404
    assert client.post("/messages", json={**body, "recipient": "boss", "body": "  "}, headers=viewer_headers).status_code == 422


@pytest.mark.parametrize("disabled, expected_status", [(True, 400), (False, 201)])
def test_messages_to_yourself_follow_the_setting(client, monkeypatch, viewer_headers, disabled, expected_status):
    from routes.users import messages

    monkeypatch.setattr(messages, "SEND_MESSAGE_TO_YOURSELF_DISABLED", disabled)
    body = {"recipient": "NewPlayer", "subject": "Hi", "body": "Hello"}
    assert client.post("/messages", json=body, headers=viewer_headers).status_code == expected_status


def test_cannot_reply_to_someone_elses_message(client, viewer_headers, admin_headers):
    client.post("/auth/register", json={"username": "third", "password": STRONG_PASSWORD})
    third = sign_in(client, "third", STRONG_PASSWORD)
    private = client.post("/messages", json={"recipient": "boss", "subject": "Hi", "body": "Secret"}, headers=third).json()

    response = client.post(
        "/messages", json={"recipient": "boss", "subject": "Hi", "body": "Hello", "reply_to": private["id"]},
        headers=viewer_headers,
    )
    assert response.status_code == 404
    assert client.post(f"/messages/{private['id']}/read", headers=viewer_headers).status_code == 404


def test_deleting_hides_a_message_for_one_side_until_both_delete(client, viewer_headers, admin_headers):
    message_id = client.post(
        "/messages", json={"recipient": "boss", "subject": "Hi", "body": "Hello"}, headers=viewer_headers
    ).json()["id"]

    assert client.delete(f"/messages/{message_id}", headers=viewer_headers).status_code == 204
    assert client.get("/messages?box=sent", headers=viewer_headers).json()["items"] == []
    assert len(client.get("/messages", headers=admin_headers).json()["items"]) == 1

    assert client.delete(f"/messages/{message_id}", headers=admin_headers).status_code == 204
    with closing(database.get_connection()) as connection:
        assert connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0


# --- mailer --------------------------------------------------------------------


def test_send_email_is_disabled_without_configuration():
    assert mailer.send_email("player@example.com", "Hi", "Hello") == mailer.STATUS_DISABLED
    assert mailer.send_email(None, "Hi", "Hello") == mailer.STATUS_NO_ADDRESS


def test_send_email_uses_smtp_when_configured(monkeypatch):
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self, context):
            sent.append("starttls")

        def login(self, username, password):
            sent.append(("login", username))

        def send_message(self, message):
            sent.append(("send", message["To"], message["Subject"]))

    monkeypatch.setattr(mailer, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(mailer, "SMTP_SECURITY", "starttls")
    monkeypatch.setattr(mailer, "SMTP_USERNAME", "mailer")
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)

    assert mailer.send_email("player@example.com", "Hi\nthere", "Hello") == mailer.STATUS_SENT
    assert sent == [
        ("connect", "smtp.example.com", mailer.SMTP_PORT),
        "starttls",
        ("login", "mailer"),
        ("send", "player@example.com", "Hi there"),
    ]


def test_send_email_reports_failures(monkeypatch):
    def refuse(*args, **kwargs):
        raise ConnectionRefusedError("no server")

    monkeypatch.setattr(mailer, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(mailer.smtplib, "SMTP", refuse)
    assert mailer.send_email("player@example.com", "Hi", "Hello") == mailer.STATUS_FAILED


@pytest.mark.parametrize("address", ["a@b", "no-at.example.com", "a b@example.com", "x" * 250 + "@example.com"])
def test_email_problem_rejects_bad_addresses(address):
    assert mailer.email_problem(address)


def test_feedback_page_is_served(client):
    response = client.get("/feedback")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
