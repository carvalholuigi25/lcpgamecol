"""Refresh token rotation, reuse detection and revocation, the web refresh cookie,
CORS for the Expo web dev server, and the client configuration endpoint."""

import time
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

import backend.auth.auth as auth
import backend.database.database as database
from helpers import rate_limiter
from main import app

ADMIN = {"username": "admin", "password": "1234"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test.db")
    auth._login_attempts.clear()
    database.initialize_database()
    with TestClient(app) as test_client:
        rate_limiter(app).requests.clear()
        yield test_client


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def sign_in(client) -> dict:
    response = client.post("/auth/token", data=ADMIN)
    assert response.status_code == 200
    client.cookies.clear()  # exercise the Bearer path unless a test opts into cookies
    return response.json()


def refresh(client, token: str):
    return client.post("/auth/refresh", headers=bearer(token))


# --- rotation ------------------------------------------------------------------------


def test_refresh_returns_a_new_refresh_token(client):
    tokens = sign_in(client)

    response = refresh(client, tokens["refresh_token"])

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["refresh_token"] != tokens["refresh_token"]
    assert client.get("/users", headers=bearer(body["access_token"])).status_code == 200
    # The new refresh token works in turn.
    assert refresh(client, body["refresh_token"]).status_code == 200


def test_a_refresh_token_works_only_once(client):
    tokens = sign_in(client)
    assert refresh(client, tokens["refresh_token"]).status_code == 200

    reused = refresh(client, tokens["refresh_token"])

    assert reused.status_code == 401
    assert reused.json()["detail"] == "Invalid refresh token"


def test_reusing_a_rotated_token_revokes_the_whole_sign_in(client):
    tokens = sign_in(client)
    rotated = refresh(client, tokens["refresh_token"]).json()["refresh_token"]

    # Someone replays the old token: the legitimate holder's current token stops working too.
    assert refresh(client, tokens["refresh_token"]).status_code == 401
    assert refresh(client, rotated).status_code == 401


def test_reuse_does_not_affect_other_sign_ins(client):
    phone = sign_in(client)
    laptop = sign_in(client)
    refresh(client, phone["refresh_token"])
    refresh(client, phone["refresh_token"])  # reuse on the phone's sign-in

    assert refresh(client, laptop["refresh_token"]).status_code == 200


def test_unknown_refresh_tokens_are_rejected(client):
    # Correctly signed but never recorded (e.g. issued before rotation existed).
    token = auth._create_token(
        "admin", "refresh", 60, extra={"fam": "family-that-does-not-exist"}
    )
    assert refresh(client, token).status_code == 401


def test_access_tokens_cannot_refresh(client):
    tokens = sign_in(client)
    assert refresh(client, tokens["access_token"]).status_code == 401


def test_refresh_keeps_the_role(client, monkeypatch):
    monkeypatch.setitem(auth.AUTH_USERS, "viewer", ("viewer-pass", auth.ROLE_VIEWER))
    login = client.post("/auth/token", data={"username": "viewer", "password": "viewer-pass"})
    client.cookies.clear()

    access = refresh(client, login.json()["refresh_token"]).json()["access_token"]

    assert client.get("/users", headers=bearer(access)).json()["role"] == auth.ROLE_VIEWER


def test_expired_rows_are_cleaned_up_on_refresh(client):
    with closing(database.get_connection()) as connection:
        connection.execute(
            "INSERT INTO refresh_tokens (jti, username, family_id, expires_at) VALUES ('old', 'admin', 'f', 1)"
        )
        connection.commit()

    refresh(client, sign_in(client)["refresh_token"])

    with closing(database.get_connection()) as connection:
        assert connection.execute("SELECT 1 FROM refresh_tokens WHERE jti = 'old'").fetchone() is None


# --- revocation ----------------------------------------------------------------------


def test_logout_revokes_the_refresh_token_sent_in_the_body(client):
    tokens = sign_in(client)

    response = client.post(
        "/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers=bearer(tokens["access_token"]),
    )

    assert response.status_code == 204
    assert refresh(client, tokens["refresh_token"]).status_code == 401


def test_logout_ends_only_the_current_sign_in(client):
    phone = sign_in(client)
    laptop = sign_in(client)

    client.post(
        "/auth/logout",
        json={"refresh_token": phone["refresh_token"]},
        headers=bearer(phone["access_token"]),
    )

    assert refresh(client, laptop["refresh_token"]).status_code == 200


def test_logout_ignores_refresh_tokens_of_other_users(client, monkeypatch):
    monkeypatch.setitem(auth.AUTH_USERS, "viewer", ("viewer-pass", auth.ROLE_VIEWER))
    admin = sign_in(client)
    viewer = client.post("/auth/token", data={"username": "viewer", "password": "viewer-pass"}).json()
    client.cookies.clear()

    response = client.post(
        "/auth/logout",
        json={"refresh_token": admin["refresh_token"]},
        headers=bearer(viewer["access_token"]),
    )

    assert response.status_code == 204
    assert refresh(client, admin["refresh_token"]).status_code == 200


def test_logout_accepts_garbage_and_no_body(client):
    tokens = sign_in(client)
    headers = bearer(tokens["access_token"])

    assert client.post("/auth/logout", json={"refresh_token": "nope"}, headers=headers).status_code == 204
    assert client.post("/auth/logout", headers=headers).status_code == 204


def test_sign_out_everywhere_revokes_refresh_tokens(client):
    tokens = sign_in(client)
    time.sleep(1.1)  # sessions_valid_after has whole-second precision in iat comparisons

    auth.revoke_sessions("admin")

    assert refresh(client, tokens["refresh_token"]).status_code == 401
    with closing(database.get_connection()) as connection:
        active = connection.execute(
            "SELECT COUNT(*) FROM refresh_tokens WHERE username = 'admin' AND revoked_at IS NULL"
        ).fetchone()[0]
    assert active == 0


# --- web refresh cookie --------------------------------------------------------------


def test_sign_in_sets_a_strict_http_only_refresh_cookie(client):
    response = client.post("/auth/token", data=ADMIN)

    cookies = response.headers.get_list("set-cookie")
    refresh_cookie = next(c for c in cookies if c.startswith(f"{auth.REFRESH_COOKIE_NAME}="))
    assert "HttpOnly" in refresh_cookie
    assert "SameSite=strict" in refresh_cookie or "SameSite=Strict" in refresh_cookie
    assert "Path=/auth" in refresh_cookie


def test_web_build_refreshes_with_the_cookie(client):
    client.post("/auth/token", data=ADMIN)
    old_cookie = client.cookies.get(auth.REFRESH_COOKIE_NAME)

    response = client.post("/auth/refresh")

    assert response.status_code == 200
    assert client.cookies.get(auth.REFRESH_COOKIE_NAME) not in (None, old_cookie)
    assert client.post("/auth/refresh").status_code == 200


def test_cookie_refresh_from_another_site_is_blocked(client):
    client.post("/auth/token", data=ADMIN)

    response = client.post("/auth/refresh", headers={"Origin": "https://evil.example"})

    assert response.status_code == 403


def test_logout_revokes_the_refresh_cookie(client):
    client.post("/auth/token", data=ADMIN)
    cookie = client.cookies.get(auth.REFRESH_COOKIE_NAME)

    response = client.post("/auth/logout")

    assert response.status_code == 204
    assert any(
        c.startswith(f"{auth.REFRESH_COOKIE_NAME}=") and "Max-Age=0" in c
        for c in response.headers.get_list("set-cookie")
    )
    client.cookies.clear()
    assert refresh(client, cookie).status_code == 401


# --- CORS and client configuration ----------------------------------------------------


@pytest.mark.parametrize("origin", ["http://localhost:8081", "http://127.0.0.1:8081"])
def test_expo_web_dev_server_is_a_trusted_origin(monkeypatch, origin):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    assert origin in auth.get_trusted_origins()


def test_cors_allows_the_expo_web_dev_server(client):
    response = client.options(
        "/auth/token",
        headers={
            "Origin": "http://localhost:8081",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:8081"


def test_client_config_defaults_to_the_requested_host(client, monkeypatch):
    monkeypatch.delenv("ASSET_BASE_URL", raising=False)

    response = client.get("/client/config")

    assert response.status_code == 200
    assert response.json() == {"api_version": app.version, "asset_base_url": "http://testserver"}


def test_client_config_uses_the_configured_asset_base_url(client, monkeypatch):
    monkeypatch.setenv("ASSET_BASE_URL", "https://cdn.example/")

    assert client.get("/client/config").json()["asset_base_url"] == "https://cdn.example"
