"""Public account routes: finishing a two-factor sign-in and resetting a forgotten password.

These run before the user has a session, so they are not behind the signed-in
router in routes/__init__.py.
"""

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from backend.auth import auth, password_reset, two_factor
from backend.mail import mailer

router = APIRouter(prefix="/auth", tags=["authentication"])

RESET_REQUEST_REPLY = (
    "If that account exists and has an email address, a reset link is on its way. "
    "Otherwise, ask an administrator for a link."
)


class ChallengeBody(BaseModel):
    challenge_token: str = Field(min_length=1, max_length=2048)


class VerifyBody(ChallengeBody):
    code: str = Field(min_length=1, max_length=32)


class ResetRequestBody(BaseModel):
    identifier: str = Field(min_length=1, max_length=254)


class ResetConfirmBody(BaseModel):
    token: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=256)


def _client_id(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _refused(error: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))


@router.post("/two-factor/verify")
def verify_two_factor(body: VerifyBody, response: Response) -> dict[str, str]:
    """Finish a sign-in with an authenticator code, an email code, or a recovery code."""
    try:
        principal = two_factor.verify_challenge(body.challenge_token, body.code)
    except two_factor.TwoFactorError as error:
        raise _refused(error) from None
    return auth.issue_session(response, principal)


@router.post("/two-factor/resend", status_code=status.HTTP_202_ACCEPTED)
def resend_two_factor_code(body: ChallengeBody, background_tasks: BackgroundTasks) -> dict[str, str]:
    try:
        username, code = two_factor.resend_challenge_code(body.challenge_token)
    except two_factor.TwoFactorError as error:
        raise _refused(error) from None
    background_tasks.add_task(two_factor.send_challenge_code, username, code)
    return {"detail": "A new code is on its way."}


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
def request_password_reset(
    body: ResetRequestBody, request: Request, background_tasks: BackgroundTasks
) -> dict[str, str]:
    try:
        pending = password_reset.request_reset(body.identifier, _client_id(request))
    except password_reset.TooManyRequests as error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(error),
            headers={"Retry-After": str(error.retry_after)},
        ) from None
    for username, token in pending:
        background_tasks.add_task(password_reset.email_link, username, token)
    return {"detail": RESET_REQUEST_REPLY}


@router.get("/password-reset/check")
def check_password_reset(token: str = Query(min_length=1, max_length=256)) -> dict:
    username = password_reset.check_token(token)
    return {"valid": username is not None, "username": username}


@router.post("/password-reset/confirm")
def confirm_password_reset(body: ResetConfirmBody, background_tasks: BackgroundTasks) -> dict[str, str]:
    try:
        username = password_reset.confirm_reset(body.token, body.password)
    except password_reset.ResetError as error:
        raise _refused(error) from None
    # Imported here so the public auth routes don't load the signed-in routes at startup.
    from routes.users.notifications import notify

    notify(username, "security", "Your password was changed", "All your other sessions were signed out.")
    background_tasks.add_task(
        mailer.send_to_user,
        username,
        "Your lcpgamecol password was changed",
        f"Hi {username},\n\nThe password of your lcpgamecol account was just changed with a reset link, "
        "and every session was signed out.\n\nIf this wasn't you, contact an administrator right away.\n",
    )
    return {"username": username, "detail": "Your password was changed. Sign in with the new one."}
