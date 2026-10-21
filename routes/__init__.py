from fastapi import APIRouter, Depends

from backend.auth.auth import get_current_user


def get_current_user_profile(username: str = Depends(get_current_user)) -> dict[str, str]:
    return {"username": username}


def __getattr__(name: str):
    if name != "router":
        raise AttributeError(name)

    from routes.achievements.routes import router as achievements_router
    from routes.admin import router as admin_router
    from routes.games.routes import router as games_router

    router = APIRouter(dependencies=[Depends(get_current_user)])
    router.add_api_route(
        "/users",
        get_current_user_profile,
        methods=["GET"],
        tags=["users"],
    )
    router.include_router(games_router)
    router.include_router(achievements_router)
    router.include_router(admin_router)
    return router