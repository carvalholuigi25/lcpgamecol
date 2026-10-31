"""Two-factor sign-in settings for the signed-in user (the Security section of /profile).

Setting up a method takes two steps (setup, then enable with a first code) so it
can't be turned on with a code the user never saw. Turning it off or making new
recovery codes asks for the password again, with the same lockout as sign-in.
"""

from types import SimpleNamespace
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from backend.auth import auth, two_factor
from backend.auth.auth import Principal, get_current_principal
from backend.gamification import xp
from routes.users.notifications import notify

router = APIRouter(prefix="/users/me/two-factor", tags=["users"])


class SetupBody(BaseModel):
    method: Literal["totp", "email"]


class CodeBody(BaseModel):
    code: str = Field(min_length=1, max_length=32)


class PasswordBody(BaseModel):
    password: str = Field(min_length=1, max_length=256)


def _refused(error: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))


def _confirm_password(principal: Principal, password: str, request: Request) -> None:
    client_id = request.client.host if request.client else "unknown"
    try:
        auth.authenticate(SimpleNamespace(username=principal.username, password=password), client_id)
    except HTTPException as error:
        if error.status_code == status.HTTP_401_UNAUTHORIZED:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That password is not right.") from None
        raise


@router.get("")
def get_two_factor(principal: Principal = Depends(get_current_principal)) -> dict:
    return two_factor.status(principal.username)


@router.post("/setup")
def setup_two_factor(body: SetupBody, principal: Principal = Depends(get_current_principal)) -> dict:
    try:
        return two_factor.start_setup(principal.username, body.method)
    except two_factor.TwoFactorError as error:
        raise _refused(error) from None


@router.post("/enable")
def enable_two_factor(body: CodeBody, principal: Principal = Depends(get_current_principal)) -> dict:
    try:
        codes = two_factor.confirm_setup(principal.username, body.code)
    except two_factor.TwoFactorError as error:
        raise _refused(error) from None
    notify(principal.username, "security", "Two-factor sign-in is on", "Keep your recovery codes somewhere safe.")
    xp.award(principal.username, "two_factor")
    return {**two_factor.status(principal.username), "recovery_codes": codes}


@router.post("/disable")
def disable_two_factor(
    body: PasswordBody, request: Request, principal: Principal = Depends(get_current_principal)
) -> dict:
    _confirm_password(principal, body.password, request)
    two_factor.disable(principal.username)
    notify(principal.username, "security", "Two-factor sign-in is off")
    return two_factor.status(principal.username)


@router.post("/recovery-codes")
def new_recovery_codes(
    body: PasswordBody, request: Request, principal: Principal = Depends(get_current_principal)
) -> dict:
    _confirm_password(principal, body.password, request)
    try:
        codes = two_factor.regenerate_recovery_codes(principal.username)
    except two_factor.TwoFactorError as error:
        raise _refused(error) from None
    return {**two_factor.status(principal.username), "recovery_codes": codes}
