import re
import time
from email import message_from_bytes, policy

import pytest
from fastapi.testclient import TestClient

import backend.auth.auth as auth
import backend.database.database as database
from backend.auth import password_reset, two_factor
from backend.mail import mailer
from main import app

STRONG_PASSWORD = "correct horse 42 battery"
NEW_PASSWORD = "purple tiger 77 lantern"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(mailer, "SMTP_HOST", "")
    monkeypatch.setattr(mailer, "MAIL_OUTBOX_DIR", str(tmp_path / "outbox"))
    monkeypatch.setitem(auth.AUTH_USERS, "boss", ("boss-pass", auth.ROLE_ADMIN))
    auth._login_attempts.clear()
    auth._registrations.clear()
    password_reset._requests.clear()
    database.initialize_database()
    with TestClient(app) as test_client:
        app.middleware_stack.app.requests.clear()
        yield test_client


@pytest.fixture()
def outbox(tmp_path):
    folder = tmp_path / "outbox"

    def read():
        return [message_from_bytes(path.read_bytes(), policy=policy.default) for path in sorted(folder.glob("*.eml"))]

    return read


def token_for(client, username, password):
    response = client.post("/auth/token", data={"username": username, "password": password})
    client.cookies.clear()
    return response


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def player(client):
    client.post("/auth/register", json={"username": "player", "password": STRONG_PASSWORD})
    body = token_for(client, "player", STRONG_PASSWORD).json()
    return bearer(body["access_token"])


def set_email(client, headers, address="player@example.com"):
    assert client.put("/users/me/profile", json={"email": address}, headers=headers).status_code == 200


def enable_totp(client, headers):
    setup = client.post("/users/me/two-factor/setup", json={"method": "totp"}, headers=headers).json()
    code = two_factor.totp_code(setup["secret"], two_factor.current_step())
    response = client.post("/users/me/two-factor/enable", json={"code": code}, headers=headers)
    assert response.status_code == 200, response.text
    # The step used to enable can't sign in again, so later codes use the next one.
    return setup["secret"], response.json()["recovery_codes"]


def next_totp(secret):
    return two_factor.totp_code(secret, two_factor.current_step() + 1)


def last_code(outbox):
    return re.search(r"\b(\d{6})\b", outbox()[-1].get_content()).group(1)


# --- TOTP algorithm ------------------------------------------------------------------


def test_totp_matches_the_rfc_6238_test_vector():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # "12345678901234567890"
    assert two_factor.totp_code(secret, 59 // 30) == "287082"
    assert two_factor.totp_code(secret, 1111111109 // 30) == "081804"


def test_totp_accepts_neighbouring_steps_but_not_used_ones():
    secret = two_factor.generate_secret()
    now = 1_000_000.0
    step = two_factor.current_step(now)
    assert two_factor.match_totp(secret, two_factor.totp_code(secret, step - 1), now=now) == step - 1
    assert two_factor.match_totp(secret, two_factor.totp_code(secret, step + 2), now=now) is None
    assert two_factor.match_totp(secret, two_factor.totp_code(secret, step), last_step=step, now=now) is None


def test_otpauth_uri_names_the_app_and_user():
    uri = two_factor.otpauth_uri("ABC", "player")
    assert uri.startswith("otpauth://totp/lcpgamecol%3Aplayer?")
    assert "secret=ABC" in uri and "issuer=lcpgamecol" in uri


# --- authenticator setup and sign-in ------------------------------------------------------


def test_status_starts_off(client, player):
    status = client.get("/users/me/two-factor", headers=player).json()
    assert status["enabled"] is False
    assert status["email_available"] is False


def test_setup_needs_a_correct_code_before_turning_on(client, player):
    setup = client.post("/users/me/two-factor/setup", json={"method": "totp"}, headers=player).json()
    assert setup["qr_code"].startswith("data:image/svg+xml")
    assert client.get("/users/me/two-factor", headers=player).json()["pending_method"] == "totp"

    assert client.post("/users/me/two-factor/enable", json={"code": "000000"}, headers=player).status_code == 400
    assert client.get("/users/me/two-factor", headers=player).json()["enabled"] is False
    # Password sign-in still works without a second step.
    assert "access_token" in token_for(client, "player", STRONG_PASSWORD).json()


def test_sign_in_with_an_authenticator_code(client, player):
    secret, codes = enable_totp(client, player)
    assert len(codes) == two_factor.RECOVERY_CODE_COUNT

    challenge = token_for(client, "player", STRONG_PASSWORD).json()
    assert challenge["two_factor_required"] is True
    assert "access_token" not in challenge
    assert "set-cookie" not in token_for(client, "player", STRONG_PASSWORD).headers

    code = next_totp(secret)
    response = client.post("/auth/two-factor/verify", json={"challenge_token": challenge["challenge_token"], "code": code})
    assert response.status_code == 200
    assert auth.AUTH_COOKIE_NAME in response.cookies
    assert client.get("/users", headers=bearer(response.json()["access_token"])).json()["username"] == "player"

    # The same challenge, and the same code, can't be used twice.
    again = token_for(client, "player", STRONG_PASSWORD).json()
    assert client.post("/auth/two-factor/verify", json={"challenge_token": challenge["challenge_token"], "code": code}).status_code == 400
    assert client.post("/auth/two-factor/verify", json={"challenge_token": again["challenge_token"], "code": code}).status_code == 400


def test_challenge_tokens_are_not_access_tokens(client, player):
    enable_totp(client, player)
    challenge = token_for(client, "player", STRONG_PASSWORD).json()["challenge_token"]
    assert client.get("/users", headers=bearer(challenge)).status_code == 401


def test_a_challenge_allows_a_few_wrong_codes(client, player):
    secret, _ = enable_totp(client, player)
    challenge = token_for(client, "player", STRONG_PASSWORD).json()["challenge_token"]
    for _ in range(two_factor.MAX_ATTEMPTS):
        assert client.post("/auth/two-factor/verify", json={"challenge_token": challenge, "code": "000000"}).status_code == 400
    response = client.post("/auth/two-factor/verify", json={"challenge_token": challenge, "code": next_totp(secret)})
    assert response.status_code == 400
    assert response.json()["detail"] == "Too many wrong codes. Sign in again."


def test_recovery_codes_work_once(client, player):
    _, codes = enable_totp(client, player)
    first = token_for(client, "player", STRONG_PASSWORD).json()["challenge_token"]
    assert client.post("/auth/two-factor/verify", json={"challenge_token": first, "code": codes[0].upper()}).status_code == 200
    second = token_for(client, "player", STRONG_PASSWORD).json()["challenge_token"]
    assert client.post("/auth/two-factor/verify", json={"challenge_token": second, "code": codes[0]}).status_code == 400
    assert client.get("/users/me/two-factor", headers=player).json()["recovery_codes_left"] == len(codes) - 1


def test_turning_off_and_new_codes_need_the_password(client, player):
    _, codes = enable_totp(client, player)
    assert client.post("/users/me/two-factor/recovery-codes", json={"password": "wrong"}, headers=player).status_code == 400
    fresh = client.post("/users/me/two-factor/recovery-codes", json={"password": STRONG_PASSWORD}, headers=player).json()
    assert set(fresh["recovery_codes"]).isdisjoint(codes)

    assert client.post("/users/me/two-factor/disable", json={"password": "wrong"}, headers=player).status_code == 400
    assert client.post("/users/me/two-factor/disable", json={"password": STRONG_PASSWORD}, headers=player).json()["enabled"] is False
    assert "access_token" in token_for(client, "player", STRONG_PASSWORD).json()


def test_configured_accounts_can_use_two_factor(client):
    boss = bearer(token_for(client, "boss", "boss-pass").json()["access_token"])
    enable_totp(client, boss)
    assert token_for(client, "boss", "boss-pass").json()["two_factor_required"] is True


# --- email codes ---------------------------------------------------------------------


def test_email_method_needs_an_address(client, player):
    response = client.post("/users/me/two-factor/setup", json={"method": "email"}, headers=player)
    assert response.status_code == 400
    assert response.json()["detail"] == "Add an email address to your profile first."


def test_email_method_needs_email_delivery(client, player, monkeypatch):
    set_email(client, player)
    monkeypatch.setattr(mailer, "MAIL_OUTBOX_DIR", "")
    response = client.post("/users/me/two-factor/setup", json={"method": "email"}, headers=player)
    assert response.status_code == 400


def test_sign_in_with_an_emailed_code(client, player, outbox, monkeypatch):
    set_email(client, player)
    setup = client.post("/users/me/two-factor/setup", json={"method": "email"}, headers=player).json()
    assert setup["email"] == "p*****@example.com"
    assert client.post("/users/me/two-factor/enable", json={"code": last_code(outbox)}, headers=player).status_code == 200
    assert client.get("/users/me/two-factor", headers=player).json()["method"] == "email"

    challenge = token_for(client, "player", STRONG_PASSWORD).json()
    assert challenge["method"] == "email"
    first_code = last_code(outbox)

    # A resend replaces the code, after a short wait.
    token = challenge["challenge_token"]
    assert client.post("/auth/two-factor/resend", json={"challenge_token": token}).status_code == 400
    monkeypatch.setattr(two_factor, "RESEND_INTERVAL_SECONDS", 0)
    assert client.post("/auth/two-factor/resend", json={"challenge_token": token}).status_code == 202
    new_code = last_code(outbox)
    if new_code != first_code:
        assert client.post("/auth/two-factor/verify", json={"challenge_token": token, "code": first_code}).status_code == 400
    assert client.post("/auth/two-factor/verify", json={"challenge_token": token, "code": new_code}).status_code == 200


def test_expired_email_codes_are_refused(client, player, outbox, monkeypatch):
    set_email(client, player)
    client.post("/users/me/two-factor/setup", json={"method": "email"}, headers=player)
    code = last_code(outbox)
    monkeypatch.setattr(two_factor.time, "time", lambda: time.monotonic() + 10**10)
    response = client.post("/users/me/two-factor/enable", json={"code": code}, headers=player)
    assert response.status_code == 400


# --- administrators -------------------------------------------------------------------------


def test_admin_can_turn_off_two_factor_for_a_locked_out_user(client, player):
    enable_totp(client, player)
    boss = bearer(token_for(client, "boss", "boss-pass").json()["access_token"])
    assert client.get("/admin/users/player", headers=boss).json()["two_factor_enabled"] is True
    assert client.delete("/admin/users/player/two-factor", headers=player).status_code == 403
    assert client.delete("/admin/users/player/two-factor", headers=boss).status_code == 204
    assert "access_token" in token_for(client, "player", STRONG_PASSWORD).json()
    assert client.get("/notifications", headers=player).json()["items"][0]["kind"] == "security"


# --- password reset ---------------------------------------------------------------------


def test_reset_request_answers_the_same_for_unknown_accounts(client, player, outbox):
    known = client.post("/auth/password-reset/request", json={"identifier": "player"})
    unknown = client.post("/auth/password-reset/request", json={"identifier": "nobody"})
    configured = client.post("/auth/password-reset/request", json={"identifier": "boss"})
    assert known.status_code == unknown.status_code == configured.status_code == 202
    assert known.json() == unknown.json() == configured.json()
    # The player has no address yet, so nothing was sent.
    assert outbox() == []


def test_reset_by_email_address_and_sign_in_with_the_new_password(client, player, outbox):
    set_email(client, player, "Player@Example.com")
    assert client.post("/auth/password-reset/request", json={"identifier": "player@example.com"}).status_code == 202
    emails = outbox()
    assert emails[0]["Subject"] == "Reset your lcpgamecol password"
    token = re.search(r"token=([\w-]+)", emails[0].get_content()).group(1)

    assert client.get(f"/auth/password-reset/check?token={token}").json() == {"valid": True, "username": "player"}
    weak = client.post("/auth/password-reset/confirm", json={"token": token, "password": "short"})
    assert weak.status_code == 400

    response = client.post("/auth/password-reset/confirm", json={"token": token, "password": NEW_PASSWORD})
    assert response.status_code == 200
    assert client.get(f"/auth/password-reset/check?token={token}").json()["valid"] is False
    assert client.post("/auth/password-reset/confirm", json={"token": token, "password": NEW_PASSWORD}).status_code == 400

    assert token_for(client, "player", STRONG_PASSWORD).status_code == 401
    assert "access_token" in token_for(client, "player", NEW_PASSWORD).json()
    assert outbox()[-1]["Subject"] == "Your lcpgamecol password was changed"


def test_reset_signs_out_existing_sessions(client, player, outbox):
    refresh = token_for(client, "player", STRONG_PASSWORD).json()["refresh_token"]
    token = password_reset.create_token("player", created_by="test")
    time.sleep(1.1)  # tokens carry whole seconds
    client.post("/auth/password-reset/confirm", json={"token": token, "password": NEW_PASSWORD})

    assert client.get("/users", headers=player).status_code == 401
    assert client.post("/auth/refresh", headers=bearer(refresh)).status_code == 401
    fresh = token_for(client, "player", NEW_PASSWORD).json()["access_token"]
    assert client.get("/users", headers=bearer(fresh)).status_code == 200


def test_reset_links_expire(client, player, monkeypatch):
    token = password_reset.create_token("player", created_by="test")
    monkeypatch.setattr(password_reset.time, "time", lambda: 10**12)
    assert client.get(f"/auth/password-reset/check?token={token}").json()["valid"] is False


def test_reset_requests_are_rate_limited(client, monkeypatch):
    monkeypatch.setattr(password_reset, "PASSWORD_RESET_MAX_PER_CLIENT", 2)
    for _ in range(2):
        assert client.post("/auth/password-reset/request", json={"identifier": "x"}).status_code == 202
    response = client.post("/auth/password-reset/request", json={"identifier": "x"})
    assert response.status_code == 429
    assert "Retry-After" in response.headers


def test_admin_reset_link(client, player, outbox):
    boss = bearer(token_for(client, "boss", "boss-pass").json()["access_token"])
    assert client.post("/admin/users/player/password-reset", headers=player).status_code == 403
    assert client.post("/admin/users/boss/password-reset", headers=boss).status_code == 400

    body = client.post("/admin/users/player/password-reset", headers=boss).json()
    assert body["emailed"] is False
    token = body["link"].split("token=")[1]
    assert client.get(f"/auth/password-reset/check?token={token}").json()["username"] == "player"

    set_email(client, player)
    assert client.post("/admin/users/player/password-reset", headers=boss).json()["emailed"] is True
    assert outbox()[-1]["To"] == "player@example.com"
    # Making a new link cancels the previous one.
    assert client.get(f"/auth/password-reset/check?token={token}").json()["valid"] is False


def test_reset_password_page_is_served(client):
    assert client.get("/reset-password").status_code == 200
