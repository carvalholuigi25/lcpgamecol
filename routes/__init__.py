from datetime import UTC, datetime

from fastapi import APIRouter, Depends

from backend.auth.auth import Principal, get_current_principal, get_current_user
from backend.gamification import xp


def get_current_user_profile(
    principal: Principal = Depends(get_current_principal),
) -> dict[str, str]:
    # Every page asks for this on load, so it is where the daily visit XP is paid.
    xp.award(principal.username, "daily_visit", datetime.now(UTC).date().isoformat())
    return {"username": principal.username, "role": principal.role}


def __getattr__(name: str):
    if name != "router":
        raise AttributeError(name)

    from routes.achievements.routes import router as achievements_router
    from routes.admin import router as admin_router
    from routes.games.igdb_imports import router as igdb_imports_router
    from routes.games.lists import router as game_lists_router
    from routes.games.moderation import admin_router as moderation_admin_router
    from routes.games.moderation import router as moderation_router
    from routes.games.reviews import router as game_reviews_router
    from routes.games.routes import router as games_router
    from routes.users.feedback import admin_router as feedback_admin_router
    from routes.users.feedback import router as feedback_router
    from routes.users.messages import router as messages_router
    from routes.users.notifications import router as notifications_router
    from routes.users.profile import router as profile_router
    from routes.users.two_factor import router as two_factor_router
    from routes.users.xp import router as xp_router

    router = APIRouter(dependencies=[Depends(get_current_user)])
    router.add_api_route(
        "/users",
        get_current_user_profile,
        methods=["GET"],
        tags=["users"],
    )
    router.include_router(profile_router)
    router.include_router(two_factor_router)
    router.include_router(xp_router)
    router.include_router(notifications_router)
    router.include_router(messages_router)
    router.include_router(feedback_router)
    router.include_router(feedback_admin_router)
    router.include_router(games_router)
    router.include_router(game_lists_router)
    router.include_router(game_reviews_router)
    router.include_router(moderation_router)
    router.include_router(moderation_admin_router)
    router.include_router(igdb_imports_router)
    router.include_router(achievements_router)
    router.include_router(admin_router)
    return router