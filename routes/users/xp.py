"""The signed-in user's XP, level and rank, and the XP leaderboard."""

from fastapi import APIRouter, Depends, Query

from backend.auth.auth import Principal, get_current_principal
from backend.gamification import xp

router = APIRouter(tags=["xp"])


@router.get("/users/me/xp")
def get_my_xp(principal: Principal = Depends(get_current_principal)) -> dict:
    return xp.describe(principal.username)


@router.get("/users/xp/leaderboard")
def get_leaderboard(limit: int = Query(default=10, ge=1, le=xp.LEADERBOARD_MAX)) -> list[dict]:
    return xp.leaderboard(limit)
