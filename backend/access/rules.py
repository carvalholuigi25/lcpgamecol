"""Site access rules: geoblocking, VPN and proxy checks, and scheduled lockdowns.

Administrators set the rules on the special features page. They are stored as one
JSON document in the access_settings table and checked for every request by
AccessControlMiddleware. Administrators are never blocked, so a rule cannot lock
them out of the dashboard; ACCESS_CONTROL_DISABLED=true turns every rule off.

Countries and VPNs are looked up by IP address with an IP intelligence service
(ip-api.com by default, see IP_LOOKUP_URL). Results are cached. Private and local
addresses are never looked up and never blocked.
"""

import ipaddress
import json
import math
import os
import re
import threading
import time
from collections import deque
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

import httpx2 as httpx
from fastapi import Request
from pydantic import BaseModel, Field, field_validator, model_validator

from backend.database import database

ACCESS_CONTROL_DISABLED = os.getenv("ACCESS_CONTROL_DISABLED", "false").lower() == "true"
# Only trust X-Forwarded-For when the app runs behind your own reverse proxy.
TRUST_PROXY_HEADERS = os.getenv("ACCESS_CONTROL_TRUST_PROXY", "false").lower() == "true"
# A header set by a CDN or proxy with the visitor's country, e.g. CF-IPCountry.
COUNTRY_HEADER = os.getenv("GEOIP_COUNTRY_HEADER", "").strip()
IP_LOOKUP_URL = os.getenv(
    "IP_LOOKUP_URL",
    "http://ip-api.com/json/{ip}?fields=status,message,countryCode,proxy,hosting",
)
IP_LOOKUP_TIMEOUT_SECONDS = float(os.getenv("IP_LOOKUP_TIMEOUT_SECONDS", "3"))
IP_LOOKUP_CACHE_SECONDS = int(os.getenv("IP_LOOKUP_CACHE_SECONDS", "3600"))
# Failed lookups are retried sooner so a short outage does not stick.
IP_LOOKUP_ERROR_CACHE_SECONDS = 60
IP_LOOKUP_CACHE_MAX_ENTRIES = 10_000
SETTINGS_CACHE_SECONDS = 5
SETTINGS_KEY = "access_control"
RECENT_BLOCKS_MAX = 50
LOCKDOWN_WINDOWS_MAX = 20
COUNTRY_PATTERN = re.compile(r"^[A-Z]{2}$")
TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

DEFAULT_LOCKDOWN_MESSAGE = "The library is closed for maintenance. Please come back later."


# --- settings -----------------------------------------------------------------


class GeoblockSettings(BaseModel):
    enabled: bool = False
    # "block" refuses the listed countries; "allow" lets in only the listed countries.
    mode: Literal["block", "allow"] = "block"
    countries: list[str] = Field(default_factory=list, max_length=250)
    # Visitors whose country cannot be found (the lookup failed) are let in unless this is on.
    block_unknown: bool = False

    @field_validator("countries")
    @classmethod
    def normalize_countries(cls, countries: list[str]) -> list[str]:
        normalized = []
        for country in countries:
            code = country.strip().upper()
            if not COUNTRY_PATTERN.fullmatch(code):
                raise ValueError(f"{country!r} is not a two-letter country code.")
            if code not in normalized:
                normalized.append(code)
        return sorted(normalized)


class VpnSettings(BaseModel):
    enabled: bool = False
    # Also refuse addresses of hosting providers and data centres, where most VPNs run.
    block_hosting: bool = False


class LockdownWindow(BaseModel):
    kind: Literal["weekly", "once"]
    # weekly: on the given days (0 = Monday) from start to end. An end before the start
    # runs past midnight, and an equal start and end closes the whole day.
    days: list[int] = Field(default_factory=list)
    start: str = "00:00"
    end: str = "00:00"
    # once: from starts_at to ends_at, both local times in the lockdown time zone.
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @field_validator("days")
    @classmethod
    def normalize_days(cls, days: list[int]) -> list[int]:
        if any(day not in range(7) for day in days):
            raise ValueError("Days go from 0 (Monday) to 6 (Sunday).")
        return sorted(set(days))

    @field_validator("start", "end")
    @classmethod
    def check_time(cls, value: str) -> str:
        if not TIME_PATTERN.fullmatch(value):
            raise ValueError("Times use the 24-hour HH:MM format.")
        return value

    @field_validator("starts_at", "ends_at")
    @classmethod
    def drop_timezone(cls, value: datetime | None) -> datetime | None:
        return value.replace(tzinfo=None, second=0, microsecond=0) if value else None

    @model_validator(mode="after")
    def check_kind(self) -> "LockdownWindow":
        if self.kind == "weekly":
            if not self.days:
                raise ValueError("Choose at least one day for a weekly lockdown.")
            self.starts_at = self.ends_at = None
        else:
            if self.starts_at is None or self.ends_at is None:
                raise ValueError("A one-time lockdown needs a start and an end.")
            if self.ends_at <= self.starts_at:
                raise ValueError("A lockdown must end after it starts.")
            self.days = []
        return self


class LockdownSettings(BaseModel):
    enabled: bool = False
    timezone: str = "UTC"
    message: str = Field(default="", max_length=300)
    windows: list[LockdownWindow] = Field(default_factory=list, max_length=LOCKDOWN_WINDOWS_MAX)

    @field_validator("timezone")
    @classmethod
    def check_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            # Windows has no system time zone database, so zoneinfo needs the tzdata package.
            if not available_timezones():
                raise ValueError(
                    "The server has no time zone data. Install the tzdata package and restart it."
                ) from None
            raise ValueError(f"{value!r} is not a known time zone.") from None
        return value

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        return value.strip()


class AccessSettings(BaseModel):
    geoblock: GeoblockSettings = Field(default_factory=GeoblockSettings)
    vpn: VpnSettings = Field(default_factory=VpnSettings)
    lockdown: LockdownSettings = Field(default_factory=LockdownSettings)

    @property
    def any_enabled(self) -> bool:
        return self.geoblock.enabled or self.vpn.enabled or self.lockdown.enabled


_settings_lock = threading.Lock()
# Keyed by database path so tests that switch databases never see stale rules.
_settings_cache: dict[str, tuple[float, AccessSettings]] = {}


def load_settings() -> AccessSettings:
    key = str(database.DATABASE_PATH)
    now = time.monotonic()
    with _settings_lock:
        cached = _settings_cache.get(key)
        if cached and now - cached[0] < SETTINGS_CACHE_SECONDS:
            return cached[1]
    with closing(database.get_connection()) as connection:
        row = connection.execute(
            "SELECT value FROM access_settings WHERE name = ?", (SETTINGS_KEY,)
        ).fetchone()
    try:
        settings = AccessSettings.model_validate_json(row["value"]) if row else AccessSettings()
    except ValueError:
        settings = AccessSettings()
    with _settings_lock:
        _settings_cache[key] = (now, settings)
    return settings


def save_settings(settings: AccessSettings, updated_by: str) -> AccessSettings:
    with closing(database.get_connection()) as connection:
        connection.execute(
            """
            INSERT INTO access_settings (name, value, updated_by, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (name) DO UPDATE SET
                value = excluded.value,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (SETTINGS_KEY, settings.model_dump_json(), updated_by, datetime.now(UTC).isoformat()),
        )
        connection.commit()
    with _settings_lock:
        _settings_cache[str(database.DATABASE_PATH)] = (time.monotonic(), settings)
    return settings


def settings_updated() -> dict | None:
    with closing(database.get_connection()) as connection:
        row = connection.execute(
            "SELECT updated_by, updated_at FROM access_settings WHERE name = ?",
            (SETTINGS_KEY,),
        ).fetchone()
    return dict(row) if row else None


# --- IP lookups -----------------------------------------------------------------


@dataclass(frozen=True)
class IpInfo:
    ip: str
    country: str | None = None
    vpn: bool = False
    hosting: bool = False
    # "private" (never looked up), "header" (country from GEOIP_COUNTRY_HEADER),
    # "lookup" (IP intelligence service) or "error" (the lookup failed).
    source: str = "lookup"

    def as_dict(self) -> dict:
        return asdict(self)


_lookup_lock = threading.Lock()
_lookup_cache: dict[str, tuple[float, IpInfo]] = {}


def client_ip(request: Request) -> str:
    if TRUST_PROXY_HEADERS:
        # Take the last address: the one your proxy added. Earlier ones come from the
        # visitor and could be forged (e.g. a private address to dodge every rule).
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[-1].strip()
        if forwarded:
            return forwarded
    return request.client.host if request.client else "unknown"


def is_valid_ip(ip: str) -> bool:
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return False
    return True


def is_public_ip(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_global
    except ValueError:
        return False


def fetch_ip_info(ip: str) -> IpInfo:
    """Ask the IP intelligence service about one address. Raises on failure."""
    with httpx.Client(timeout=IP_LOOKUP_TIMEOUT_SECONDS) as client:
        response = client.get(IP_LOOKUP_URL.format(ip=ip))
        response.raise_for_status()
        body = response.json()
    if body.get("status", "success") != "success":
        raise ValueError(body.get("message") or "lookup failed")
    country = (body.get("countryCode") or "").upper() or None
    return IpInfo(
        ip=ip,
        country=country if country and COUNTRY_PATTERN.fullmatch(country) else None,
        vpn=bool(body.get("proxy")),
        hosting=bool(body.get("hosting")),
    )


def lookup_ip(ip: str) -> IpInfo:
    if not is_public_ip(ip):
        return IpInfo(ip=ip, source="private")
    now = time.monotonic()
    with _lookup_lock:
        cached = _lookup_cache.get(ip)
        if cached and cached[0] > now:
            return cached[1]
    try:
        info = fetch_ip_info(ip)
        lifetime = IP_LOOKUP_CACHE_SECONDS
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        info = IpInfo(ip=ip, source="error")
        lifetime = IP_LOOKUP_ERROR_CACHE_SECONDS
    with _lookup_lock:
        if len(_lookup_cache) >= IP_LOOKUP_CACHE_MAX_ENTRIES:
            for expired in [key for key, (expires, _) in _lookup_cache.items() if expires <= now]:
                del _lookup_cache[expired]
            if len(_lookup_cache) >= IP_LOOKUP_CACHE_MAX_ENTRIES:
                _lookup_cache.clear()
        _lookup_cache[ip] = (now + lifetime, info)
    return info


def clear_caches() -> None:
    with _lookup_lock:
        _lookup_cache.clear()
    with _settings_lock:
        _settings_cache.clear()
    with _blocks_lock:
        _recent_blocks.clear()


# --- rules ----------------------------------------------------------------------


@dataclass(frozen=True)
class Decision:
    reason: Literal["geoblock", "vpn", "lockdown"]
    message: str
    status_code: int
    retry_after: int | None = None
    country: str | None = None
    custom_message: bool = False


def _window_end(window: LockdownWindow, now: datetime) -> datetime | None:
    """The local time an active window ends, or None when it is not active now."""
    if window.kind == "once":
        local = now.replace(tzinfo=None)
        if window.starts_at <= local < window.ends_at:
            return window.ends_at.replace(tzinfo=now.tzinfo)
        return None

    start = datetime.strptime(window.start, "%H:%M").time()
    end = datetime.strptime(window.end, "%H:%M").time()
    today, current = now.date(), now.timetz().replace(tzinfo=None)
    weekday = today.weekday()
    yesterday_listed = (weekday - 1) % 7 in window.days

    def at(day: date, moment) -> datetime:
        return datetime.combine(day, moment, tzinfo=now.tzinfo)

    # An equal start and end is a 24-hour window, so it runs past midnight like start > end.
    if start < end:
        if weekday in window.days and start <= current < end:
            return at(today, end)
        return None
    if weekday in window.days and current >= start:
        return at(today + timedelta(days=1), end)
    if yesterday_listed and current < end:
        return at(today, end)
    return None


def active_lockdown(settings: LockdownSettings, now: datetime | None = None) -> datetime | None:
    """When lockdown is on now, the time the current window ends (the latest of any overlaps)."""
    if not settings.enabled:
        return None
    zone = ZoneInfo(settings.timezone)
    now = (now or datetime.now(UTC)).astimezone(zone)
    ends = [end for window in settings.windows if (end := _window_end(window, now))]
    return max(ends) if ends else None


def geoblock_refuses(settings: GeoblockSettings, info: IpInfo) -> bool:
    if not settings.enabled or info.source == "private":
        return False
    if info.country is None:
        return settings.block_unknown
    listed = info.country in settings.countries
    return listed if settings.mode == "block" else not listed


def vpn_refuses(settings: VpnSettings, info: IpInfo) -> bool:
    if not settings.enabled:
        return False
    return info.vpn or (settings.block_hosting and info.hosting)


def needs_lookup(settings: AccessSettings, has_country_header: bool) -> bool:
    return settings.vpn.enabled or (settings.geoblock.enabled and not has_country_header)


def evaluate(settings: AccessSettings, info: IpInfo, now: datetime | None = None) -> Decision | None:
    lockdown_end = active_lockdown(settings.lockdown, now)
    if lockdown_end is not None:
        remaining = (lockdown_end - (now or datetime.now(UTC))).total_seconds()
        return Decision(
            reason="lockdown",
            message=settings.lockdown.message or DEFAULT_LOCKDOWN_MESSAGE,
            status_code=503,
            retry_after=max(1, math.ceil(remaining)),
            custom_message=bool(settings.lockdown.message),
        )
    if geoblock_refuses(settings.geoblock, info):
        return Decision(
            reason="geoblock",
            message="The library is not available in your country or region.",
            status_code=403,
            country=info.country,
        )
    if vpn_refuses(settings.vpn, info):
        return Decision(
            reason="vpn",
            message="The library cannot be used through a VPN or proxy. Turn it off and try again.",
            status_code=403,
        )
    return None


def ip_info_for_request(request: Request, settings: AccessSettings) -> IpInfo:
    ip = client_ip(request)
    header_country = request.headers.get(COUNTRY_HEADER, "").strip().upper() if COUNTRY_HEADER else ""
    if not COUNTRY_PATTERN.fullmatch(header_country):
        header_country = ""
    if not is_public_ip(ip):
        return IpInfo(ip=ip, source="private")
    if not needs_lookup(settings, bool(header_country)):
        return IpInfo(ip=ip, country=header_country or None, source="header")
    info = lookup_ip(ip)
    if header_country:
        return IpInfo(ip=ip, country=header_country, vpn=info.vpn, hosting=info.hosting, source="header")
    return info


# --- recent blocks ----------------------------------------------------------------

_blocks_lock = threading.Lock()
_recent_blocks: deque[dict] = deque(maxlen=RECENT_BLOCKS_MAX)


def record_block(decision: Decision, info: IpInfo, path: str) -> None:
    with _blocks_lock:
        _recent_blocks.appendleft(
            {
                "at": datetime.now(UTC).isoformat(),
                "reason": decision.reason,
                "ip": info.ip,
                "country": info.country,
                "path": path[:200],
            }
        )


def recent_blocks() -> list[dict]:
    with _blocks_lock:
        return list(_recent_blocks)


def describe(settings: AccessSettings) -> dict:
    lockdown_end = active_lockdown(settings.lockdown)
    return {
        "settings": json.loads(settings.model_dump_json()),
        "status": {
            "disabled_by_server": ACCESS_CONTROL_DISABLED,
            "lockdown_active": lockdown_end is not None,
            "lockdown_ends_at": lockdown_end.isoformat() if lockdown_end else None,
            "country_header": COUNTRY_HEADER or None,
            "trust_proxy_headers": TRUST_PROXY_HEADERS,
        },
        "updated": settings_updated(),
        "recent_blocks": recent_blocks(),
    }
