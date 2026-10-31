"""Administrator switches that only work while developing (APP_ENV=development)."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.auth import two_factor
from backend.auth.auth import Principal, require_admin

router = APIRouter(prefix="/admin/development", tags=["admin"])


class DevBypassUpdate(BaseModel):
    enabled: bool


@router.get("/two-factor")
def get_two_factor_bypass() -> dict:
    return two_factor.dev_bypass_status()


@router.put("/two-factor")
def update_two_factor_bypass(body: DevBypassUpdate, principal: Principal = Depends(require_admin)) -> dict:
    try:
        return two_factor.set_dev_bypass(body.enabled, principal.username)
    except two_factor.TwoFactorError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from None
