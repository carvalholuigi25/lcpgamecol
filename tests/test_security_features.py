import pytest
from fastapi.testclient import TestClient

import backend.auth.auth as auth
import backend.auth.users as users
import backend.database.database as database
import routes.admin.uploads as uploads
from main import app

STRONG_PASSWORD = "correct horse 42 battery"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF_BYTES = b"%PDF-1.7\n%test\n"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(uploads, "UPLOAD_DIRECTORY", tmp_path / "uploads")
    auth._login_attempts.clear()
    auth._registrations.clear()
    database.initialize_database()
    with TestClient(app) as test_client:
        app.middleware_stack.app.requests.clear()
        yield test_client


@pytest.fixture()
def admin_headers(client):
    response = client.post("/auth/token", data={"username": "admin", "password": "1234"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def register(client, username="newplayer", password=STRONG_PASSWORD):
    return client.post("/auth/register", json={"username": username, "password": password})


# --- password hashing and policy ------------------------------------------------


def test_password_hash_round_trip_and_salt():
    first = users.hash_password(STRONG_PASSWORD)
    second = users.hash_password(STRONG_PASSWORD)

    assert first != second
    assert users.is_password_hash(first)
    assert users.verify_password(STRONG_PASSWORD, first)
    assert not users.verify_password("wrong password 1", first)
    assert not users.verify_password(STRONG_PASSWORD, "scrypt$broken")
    assert not users.verify_password(STRONG_PASSWORD, "plaintext")


@pytest.mark.parametrize(
    "password, username, problem",
    [
        ("short1", "", "at least"),
        ("x" * 129 + "1", "", "or fewer"),
        (" padded password 1", "", "spaces"),
        ("myname-is-great-1", "MyName", "username"),
        ("password1234", "", "common"),
        ("aaaaaaaaaaaa1", "", "common"),
        ("onlyletterswords", "", "Mix letters"),
    ],
)
def test_password_policy_rejects_weak_passwords(password, username, problem):
    assert problem in users.password_problem(password, username)


def test_password_policy_accepts_strong_password():
    assert users.password_problem(STRONG_PASSWORD, "newplayer") is None


@pytest.mark.parametrize("username", ["ab", "-starts-with-dash", "has space", "x" * 33, "bad/char"])
def test_username_policy_rejects_invalid_names(username):
    assert users.username_problem(username)


def test_configured_users_accept_password_hashes(client, monkeypatch):
    monkeypatch.setitem(
        auth.AUTH_USERS, "hashed", (users.hash_password(STRONG_PASSWORD), auth.ROLE_ADMIN)
    )

    response = client.post("/auth/token", data={"username": "hashed", "password": STRONG_PASSWORD})

    assert response.status_code == 200


def test_non_ascii_password_is_rejected_without_error(client):
    response = client.post("/auth/token", data={"username": "admin", "password": "pässwörd"})

    assert response.status_code == 401


# --- registration -------------------------------------------------------------------


def test_registration_creates_viewer_that_can_sign_in(client):
    response = register(client)

    assert response.status_code == 201
    assert response.json() == {"username": "newplayer", "role": "viewer"}

    login = client.post("/auth/token", data={"username": "NewPlayer", "password": STRONG_PASSWORD})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/users", headers=headers).json() == {
        "username": "newplayer",
        "role": "viewer",
    }
    assert client.get("/games", headers=headers).status_code == 200
    assert client.get("/admin/dashboard", headers=headers).status_code == 403

    refreshed = client.post(
        "/auth/refresh",
        headers={"Authorization": f"Bearer {login.json()['refresh_token']}"},
    )
    assert refreshed.status_code == 200


def test_registration_stores_only_a_password_hash(client):
    register(client)

    row = users.get_user("newplayer")
    assert row["password_hash"] != STRONG_PASSWORD
    assert STRONG_PASSWORD not in row["password_hash"]
    assert users.verify_password(STRONG_PASSWORD, row["password_hash"])


def test_registration_rejects_duplicates_case_insensitively(client):
    assert register(client).status_code == 201

    duplicate = register(client, username="NEWPLAYER")
    configured = register(client, username="Admin")

    assert duplicate.status_code == 409
    assert configured.status_code == 409
    assert duplicate.json()["detail"] == "That username is not available."


@pytest.mark.parametrize(
    "username, password",
    [("ab", STRONG_PASSWORD), ("newplayer", "short"), ("newplayer", "newplayer-pass-1")],
)
def test_registration_enforces_policy(client, username, password):
    response = register(client, username=username, password=password)

    assert response.status_code == 400
    assert isinstance(response.json()["detail"], str)


def test_registration_is_throttled_per_client(client, monkeypatch):
    monkeypatch.setattr(auth, "REGISTRATION_MAX_PER_CLIENT", 2)

    assert register(client, username="player1").status_code == 201
    assert register(client, username="player2").status_code == 201
    blocked = register(client, username="player3")

    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0


def test_registration_can_be_disabled(client, monkeypatch):
    monkeypatch.setattr(auth, "REGISTRATION_ENABLED", False)

    assert register(client).status_code == 403


def test_login_lockout_is_case_insensitive(client):
    for username in ("admin", "ADMIN"):
        assert client.post("/auth/token", data={"username": username, "password": "x"}).status_code == 401
    locked = client.post("/auth/token", data={"username": "Admin", "password": "x"})

    assert locked.status_code == 429


def test_auth_responses_are_not_cached(client):
    response = client.post("/auth/token", data={"username": "admin", "password": "1234"})

    assert response.headers["cache-control"] == "no-store"


# --- CSRF protection for cookie sessions -------------------------------------------


def test_cookie_writes_from_other_sites_are_blocked(client):
    client.post("/auth/token", data={"username": "admin", "password": "1234"})

    blocked = client.post("/auth/logout", headers={"Origin": "https://evil.example"})
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "Cross-site request blocked"

    trusted = client.post("/auth/logout", headers={"Origin": "http://localhost:3000"})
    assert trusted.status_code == 204


def test_cookie_writes_from_same_origin_are_allowed(client):
    client.post("/auth/token", data={"username": "admin", "password": "1234"})

    response = client.post("/auth/logout", headers={"Origin": "http://testserver"})

    assert response.status_code == 204


def test_cookie_reads_from_other_sites_are_not_blocked(client):
    client.post("/auth/token", data={"username": "admin", "password": "1234"})

    response = client.get("/users", headers={"Origin": "https://evil.example"})

    assert response.status_code == 200


# --- safe file uploads ---------------------------------------------------------------


def upload(client, headers, name="cover.png", content=PNG_BYTES, content_type="image/png"):
    return client.post("/admin/uploads", files={"file": (name, content, content_type)}, headers=headers)


def test_upload_list_download_and_delete(client, admin_headers):
    created = upload(client, admin_headers)

    assert created.status_code == 201
    record = created.json()
    assert record["original_name"] == "cover.png"
    assert record["content_type"] == "image/png"
    assert record["size_bytes"] == len(PNG_BYTES)
    assert record["uploaded_by"] == "admin"
    assert record["previewable"] is True
    stored = list(uploads.UPLOAD_DIRECTORY.iterdir())
    assert [path.name for path in stored] == [f"{record['id']}.png"]

    listed = client.get("/admin/uploads", headers=admin_headers).json()
    assert [item["id"] for item in listed] == [record["id"]]

    download = client.get(f"/admin/uploads/{record['id']}", headers=admin_headers)
    assert download.status_code == 200
    assert download.content == PNG_BYTES
    assert download.headers["content-disposition"].startswith("attachment")
    assert "sandbox" in download.headers["content-security-policy"]
    assert download.headers["x-content-type-options"] == "nosniff"

    preview = client.get(f"/admin/uploads/{record['id']}?inline=true", headers=admin_headers)
    assert preview.headers["content-disposition"].startswith("inline")

    deleted = client.delete(f"/admin/uploads/{record['id']}", headers=admin_headers)
    assert deleted.status_code == 204
    assert list(uploads.UPLOAD_DIRECTORY.iterdir()) == []
    assert client.get(f"/admin/uploads/{record['id']}", headers=admin_headers).status_code == 404


def test_pdf_uploads_are_never_served_inline(client, admin_headers):
    record = upload(client, admin_headers, "manual.pdf", PDF_BYTES, "application/pdf").json()

    preview = client.get(f"/admin/uploads/{record['id']}?inline=true", headers=admin_headers)

    assert record["previewable"] is False
    assert preview.headers["content-disposition"].startswith("attachment")


@pytest.mark.parametrize(
    "name, content, content_type",
    [
        ("evil.svg", b"<svg onload=alert(1)>", "image/svg+xml"),
        ("page.html", b"<script>alert(1)</script>", "text/html"),
        ("fake.png", b"<script>alert(1)</script>", "image/png"),
        ("cover.pdf", PNG_BYTES, "application/pdf"),
        ("noextension", PNG_BYTES, "image/png"),
    ],
)
def test_uploads_with_disallowed_content_are_rejected(client, admin_headers, name, content, content_type):
    response = upload(client, admin_headers, name, content, content_type)

    assert response.status_code == 415
    assert client.get("/admin/uploads", headers=admin_headers).json() == []
    assert not uploads.UPLOAD_DIRECTORY.exists() or list(uploads.UPLOAD_DIRECTORY.iterdir()) == []


def test_empty_uploads_are_rejected(client, admin_headers):
    response = upload(client, admin_headers, content=b"")

    assert response.status_code == 400


def test_oversized_uploads_are_rejected(client, admin_headers, monkeypatch):
    monkeypatch.setattr(uploads, "UPLOAD_MAX_BYTES", 32)

    response = upload(client, admin_headers)

    assert response.status_code == 413
    assert list(uploads.UPLOAD_DIRECTORY.iterdir()) == []


def test_oversized_request_bodies_are_rejected_before_parsing(client, admin_headers, monkeypatch):
    monkeypatch.setattr(uploads, "UPLOAD_MAX_BYTES", 16)
    monkeypatch.setattr(uploads, "MULTIPART_OVERHEAD_BYTES", 16)

    response = upload(client, admin_headers, content=PNG_BYTES * 4)

    assert response.status_code == 413


def test_upload_storage_limit(client, admin_headers, monkeypatch):
    monkeypatch.setattr(uploads, "UPLOAD_MAX_FILES", 1)

    assert upload(client, admin_headers).status_code == 201
    assert upload(client, admin_headers).status_code == 409


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("../../etc/passwd.png", "passwd.png"),
        ("C:\\Windows\\evil.png", "evil.png"),
        ('bad<>:"|?*name.png', "bad_______name.png"),
        ("line\nbreak\x00.png", "linebreak.png"),
        ("...", "upload"),
        ("", "upload"),
        ("a" * 200 + ".png", "a" * 116 + ".png"),
    ],
)
def test_sanitize_filename(filename, expected):
    assert uploads.sanitize_filename(filename) == expected


def test_uploads_require_admin(client, monkeypatch):
    assert client.get("/admin/uploads").status_code == 401

    monkeypatch.setitem(auth.AUTH_USERS, "viewer", ("viewer-pass", auth.ROLE_VIEWER))
    login = client.post("/auth/token", data={"username": "viewer", "password": "viewer-pass"})
    viewer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert client.get("/admin/uploads", headers=viewer_headers).status_code == 403
    assert upload(client, viewer_headers).status_code == 403


def test_invalid_upload_ids_are_rejected(client, admin_headers):
    assert client.get("/admin/uploads/..%2Fsecret", headers=admin_headers).status_code in (404, 422)
    assert client.get("/admin/uploads/" + "0" * 32, headers=admin_headers).status_code == 404


def test_upload_limits_endpoint(client, admin_headers):
    limits = client.get("/admin/uploads/limits", headers=admin_headers).json()

    assert limits["max_bytes"] == uploads.UPLOAD_MAX_BYTES
    assert limits["allowed_types"]["image/jpeg"] == [".jpg", ".jpeg"]
    assert "image/svg+xml" not in limits["allowed_types"]


def test_special_features_page_is_served(client):
    response = client.get("/admin/special-features")

    assert response.status_code == 200
    assert "Safe file upload" in response.text
