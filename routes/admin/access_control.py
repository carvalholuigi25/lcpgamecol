"""Administrator endpoints for the site access rules (geoblock, VPN checker, lockdown)."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from starlette.concurrency import run_in_threadpool

from backend.access import rules
from backend.auth.auth import Principal, require_admin

router = APIRouter(prefix="/admin/access-control", tags=["admin"])


@router.get("")
def get_access_control() -> dict:
    return rules.describe(rules.load_settings())


@router.put("")
def update_access_control(
    body: rules.AccessSettings,
    principal: Principal = Depends(require_admin),
) -> dict:
    return rules.describe(rules.save_settings(body, principal.username))


@router.get("/check-ip")
async def check_ip(
    request: Request,
    ip: str | None = Query(default=None, max_length=64, description="Defaults to your own address."),
) -> dict:
    """Look up an address and say whether the current rules would let it in."""
    address = (ip or rules.client_ip(request)).strip()
    if ip is not None and not rules.is_valid_ip(address):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Enter a valid IPv4 or IPv6 address.",
        )
    settings = await run_in_threadpool(rules.load_settings)
    info = await run_in_threadpool(rules.lookup_ip, address)
    decision = rules.evaluate(settings, info)
    return {
        **info.as_dict(),
        "blocked": decision is not None,
        "reason": decision.reason if decision else None,
        "geoblocked": rules.geoblock_refuses(settings.geoblock, info),
        "vpn_blocked": rules.vpn_refuses(settings.vpn, info),
    }
