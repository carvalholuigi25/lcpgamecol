from fastapi import APIRouter, Depends

from backend.auth.auth import Principal, get_current_principal, get_current_user


def get_current_user_profile(
    principal: Principal = Depends(get_current_principal),
) -> dict[str, str]:
    return {"username": principal.username, "role": principal.role}


def __getattr__(name: str):
    if name != "router":
        raise AttributeError(name)

    from routes.achievements.routes import router as achievements_router
    from routes.admin import router as admin_router
    from routes.games.igdb_imports import router as igdb_imports_router
    from routes.games.lists import router as game_lists_router
    from routes.games.routes import router as games_router
    from routes.users.profile import router as profile_router

    router = APIRouter(dependencies=[Depends(get_current_user)])
    router.add_api_route(
        "/users",
        get_current_user_profile,
        methods=["GET"],
        tags=["users"],
    )
    router.include_router(profile_router)
    router.include_router(games_router)
    router.include_router(game_lists_router)
    router.include_router(igdb_imports_router)
    router.include_router(achievements_router)
    router.include_router(admin_router)
    return router