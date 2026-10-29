from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

import backend.access.rules as rules
import backend.auth.auth as auth
import backend.database.database as database
from main import app

PUBLIC_IP = "8.8.8.8"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(rules, "TRUST_PROXY_HEADERS", True)
    auth._login_attempts.clear()
    rules.clear_caches()
    database.initialize_database()
    with TestClient(app) as test_client:
        app.middleware_stack.app.requests.clear()
        yield test_client
    rules.clear_caches()


@pytest.fixture()
def admin_headers(client):
    response = client.post("/auth/token", data={"username": "admin", "password": "1234"})
    # Only requests that pass these headers should count as the administrator.
    client.cookies.clear()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture()
def lookups(monkeypatch):
    """Fake IP intelligence answers, keyed by address."""
    answers: dict[str, rules.IpInfo] = {}
    calls: list[str] = []

    def fake_fetch(ip):
        calls.append(ip)
        if ip not in answers:
            raise ValueError("unknown")
        return answers[ip]

    monkeypatch.setattr(rules, "fetch_ip_info", fake_fetch)
    return answers, calls


def visit(client, ip=PUBLIC_IP, path="/games", **kwargs):
    headers = {"X-Forwarded-For": ip, **kwargs.pop("headers", {})}
    return client.get(path, headers=headers, **kwargs)


def save(client, admin_headers, **sections):
    body = {"geoblock": {}, "vpn": {}, "lockdown": {}, **sections}
    response = client.put("/admin/access-control", json=body, headers=admin_headers)
    assert response.status_code == 200, response.text
    return response.json()


# --- rules ---------------------------------------------------------------------


def test_geoblock_block_and_allow_modes():
    portugal = rules.IpInfo(ip=PUBLIC_IP, country="PT")
    block = rules.GeoblockSettings(enabled=True, mode="block", countries=["pt"])
    allow = rules.GeoblockSettings(enabled=True, mode="allow", countries=["ES"])

    assert block.countries == ["PT"]
    assert rules.geoblock_refuses(block, portugal)
    assert rules.geoblock_refuses(allow, portugal)
    assert not rules.geoblock_refuses(allow, rules.IpInfo(ip=PUBLIC_IP, country="ES"))
    assert not rules.geoblock_refuses(block, rules.IpInfo(ip="10.0.0.1", source="private"))


def test_geoblock_unknown_country_follows_setting():
    unknown = rules.IpInfo(ip=PUBLIC_IP, source="error")
    assert not rules.geoblock_refuses(rules.GeoblockSettings(enabled=True), unknown)
    assert rules.geoblock_refuses(rules.GeoblockSettings(enabled=True, block_unknown=True), unknown)


def test_geoblock_rejects_bad_country_codes():
    with pytest.raises(ValueError):
        rules.GeoblockSettings(countries=["Portugal"])


def test_vpn_and_hosting_detection():
    vpn = rules.IpInfo(ip=PUBLIC_IP, vpn=True)
    hosting = rules.IpInfo(ip=PUBLIC_IP, hosting=True)

    assert rules.vpn_refuses(rules.VpnSettings(enabled=True), vpn)
    assert not rules.vpn_refuses(rules.VpnSettings(enabled=True), hosting)
    assert rules.vpn_refuses(rules.VpnSettings(enabled=True, block_hosting=True), hosting)
    assert not rules.vpn_refuses(rules.VpnSettings(enabled=False), vpn)


@pytest.mark.parametrize(
    "now, active",
    [
        (datetime(2026, 10, 26, 22, 30, tzinfo=UTC), True),  # Monday, after the start
        (datetime(2026, 10, 27, 5, 59, tzinfo=UTC), True),  # Tuesday, before the end
        (datetime(2026, 10, 27, 6, 0, tzinfo=UTC), False),  # Tuesday, at the end
        (datetime(2026, 10, 27, 22, 30, tzinfo=UTC), False),  # Tuesday is not listed
    ],
)
def test_weekly_lockdown_across_midnight(now, active):
    settings = rules.LockdownSettings(
        enabled=True,
        windows=[{"kind": "weekly", "days": [0], "start": "22:00", "end": "06:00"}],
    )
    assert (rules.active_lockdown(settings, now) is not None) is active


def test_weekly_lockdown_uses_time_zone():
    settings = rules.LockdownSettings(
        enabled=True,
        timezone="Asia/Tokyo",
        windows=[{"kind": "weekly", "days": [0, 1, 2, 3, 4, 5, 6], "start": "09:00", "end": "10:00"}],
    )
    # 00:30 UTC is 09:30 in Tokyo.
    end = rules.active_lockdown(settings, datetime(2026, 10, 29, 0, 30, tzinfo=UTC))
    assert end is not None and end.astimezone(UTC).hour == 1
    assert rules.active_lockdown(settings, datetime(2026, 10, 29, 9, 30, tzinfo=UTC)) is None


def test_one_time_lockdown_and_validation():
    settings = rules.LockdownSettings(
        enabled=True,
        windows=[{"kind": "once", "starts_at": "2026-12-24T18:00", "ends_at": "2026-12-26T08:00"}],
    )
    assert rules.active_lockdown(settings, datetime(2026, 12, 25, 12, tzinfo=UTC))
    assert rules.active_lockdown(settings, datetime(2026, 12, 26, 9, tzinfo=UTC)) is None
    assert rules.active_lockdown(settings.model_copy(update={"enabled": False}), datetime(2026, 12, 25, 12, tzinfo=UTC)) is None

    with pytest.raises(ValueError):
        rules.LockdownWindow(kind="once", starts_at="2026-12-26T08:00", ends_at="2026-12-24T08:00")
    with pytest.raises(ValueError):
        rules.LockdownWindow(kind="weekly", days=[], start="22:00", end="06:00")
    with pytest.raises(ValueError):
        rules.LockdownSettings(timezone="Mars/Olympus")


def test_lookup_caches_results_and_skips_private_addresses(lookups):
    answers, calls = lookups
    answers[PUBLIC_IP] = rules.IpInfo(ip=PUBLIC_IP, country="US")

    assert rules.lookup_ip(PUBLIC_IP).country == "US"
    assert rules.lookup_ip(PUBLIC_IP).country == "US"
    assert rules.lookup_ip("192.168.1.10").source == "private"
    assert rules.lookup_ip("1.1.1.1").source == "error"
    assert calls == [PUBLIC_IP, "1.1.1.1"]
    rules.clear_caches()


# --- middleware and endpoints ----------------------------------------------------


def test_settings_require_admin(client):
    assert client.get("/admin/access-control").status_code == 401
    assert client.put("/admin/access-control", json={}).status_code == 401


def test_nothing_is_blocked_by_default(client, lookups):
    _, calls = lookups
    assert visit(client).status_code != 403
    assert calls == []


def test_geoblock_blocks_listed_country(client, admin_headers, lookups):
    answers, _ = lookups
    answers[PUBLIC_IP] = rules.IpInfo(ip=PUBLIC_IP, country="RU")
    answers["1.1.1.1"] = rules.IpInfo(ip="1.1.1.1", country="PT")
    data = save(client, admin_headers, geoblock={"enabled": True, "countries": ["RU"]})
    assert data["settings"]["geoblock"]["countries"] == ["RU"]

    blocked = visit(client)
    assert blocked.status_code == 403
    assert blocked.json() == {
        "detail": "The library is not available in your country or region.",
        "reason": "geoblock",
    }
    assert visit(client, ip="1.1.1.1").status_code != 403

    page = visit(client, path="/library", headers={"Accept": "text/html"})
    assert page.status_code == 403
    assert "Not available in your region" in page.text

    recent = client.get("/admin/access-control", headers=admin_headers).json()["recent_blocks"]
    assert recent[0]["reason"] == "geoblock" and recent[0]["country"] == "RU"


def test_country_header_skips_lookup(client, admin_headers, lookups, monkeypatch):
    _, calls = lookups
    monkeypatch.setattr(rules, "COUNTRY_HEADER", "CF-IPCountry")
    save(client, admin_headers, geoblock={"enabled": True, "mode": "allow", "countries": ["PT"]})

    assert visit(client, headers={"CF-IPCountry": "PT"}).status_code != 403
    assert visit(client, headers={"CF-IPCountry": "FR"}).status_code == 403
    assert calls == []


def test_vpn_checker_blocks_vpn(client, admin_headers, lookups):
    answers, _ = lookups
    answers[PUBLIC_IP] = rules.IpInfo(ip=PUBLIC_IP, country="NL", vpn=True)
    save(client, admin_headers, vpn={"enabled": True})

    response = visit(client)
    assert response.status_code == 403
    assert response.json()["reason"] == "vpn"


def test_admins_and_sign_in_are_never_blocked(client, admin_headers, lookups):
    answers, _ = lookups
    answers[PUBLIC_IP] = rules.IpInfo(ip=PUBLIC_IP, country="RU", vpn=True)
    save(client, admin_headers, geoblock={"enabled": True, "countries": ["RU"]}, vpn={"enabled": True})

    assert visit(client, headers=admin_headers).status_code == 200
    token = client.post(
        "/auth/token",
        data={"username": "admin", "password": "1234"},
        headers={"X-Forwarded-For": PUBLIC_IP},
    )
    assert token.status_code == 200
    client.cookies.clear()
    assert visit(client, path="/admin").status_code == 200
    assert visit(client, path="/public/styles/css/error.css").status_code == 200


def test_lockdown_returns_503_with_retry_after(client, admin_headers, lookups):
    every_day = {"kind": "weekly", "days": list(range(7)), "start": "00:00", "end": "00:00"}
    data = save(
        client,
        admin_headers,
        lockdown={"enabled": True, "message": "Back <soon>", "windows": [every_day]},
    )
    assert data["status"]["lockdown_active"] is True

    response = visit(client, ip="127.0.0.1")
    assert response.status_code == 503
    assert response.json()["reason"] == "lockdown"
    assert int(response.headers["Retry-After"]) > 0

    page = visit(client, ip="127.0.0.1", path="/library", headers={"Accept": "text/html"})
    assert "Back &lt;soon&gt;" in page.text
    assert 'translate="no"' in page.text

    assert visit(client, ip="127.0.0.1", headers=admin_headers).status_code == 200


def test_invalid_settings_are_rejected(client, admin_headers):
    response = client.put(
        "/admin/access-control",
        json={"lockdown": {"enabled": True, "timezone": "Nowhere/City"}},
        headers=admin_headers,
    )
    assert response.status_code == 422


def test_check_ip_reports_decision(client, admin_headers, lookups):
    answers, _ = lookups
    answers[PUBLIC_IP] = rules.IpInfo(ip=PUBLIC_IP, country="US", vpn=True, hosting=True)
    save(client, admin_headers, vpn={"enabled": True})

    result = client.get(f"/admin/access-control/check-ip?ip={PUBLIC_IP}", headers=admin_headers).json()
    assert result["country"] == "US"
    assert result["vpn"] is True
    assert result["blocked"] is True and result["reason"] == "vpn"
    assert result["geoblocked"] is False

    bad = client.get("/admin/access-control/check-ip?ip=not-an-ip", headers=admin_headers)
    assert bad.status_code == 422
