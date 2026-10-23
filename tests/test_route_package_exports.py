import builtins
import importlib

import pytest
from fastapi import APIRouter, FastAPI


ROUTE_PACKAGES = [
    ("routes.games", "routes.games.routes"),
    ("routes.achievements", "routes.achievements.routes"),
]


@pytest.mark.parametrize("package_name, route_module_name", ROUTE_PACKAGES)
def test_route_package_exposes_router_lazily(
    monkeypatch, package_name, route_module_name
):
    package = importlib.import_module(package_name)
    imported_modules = []
    original_import = builtins.__import__

    def track_route_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == route_module_name:
            imported_modules.append(name)
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", track_route_import)

    importlib.reload(package)
    assert imported_modules == []

    router = package.router

    assert package.__all__ == ["router"]
    assert isinstance(router, APIRouter)
    assert imported_modules == [route_module_name]
    assert package.router is router
    assert imported_modules == [route_module_name, route_module_name]


@pytest.mark.parametrize("package_name, _", ROUTE_PACKAGES)
def test_route_package_rejects_unknown_exports(package_name, _):
    package = importlib.import_module(package_name)

    with pytest.raises(AttributeError) as exc_info:
        package.unknown_export

    assert str(exc_info.value) == "unknown_export"


def test_root_route_package_exposes_router_lazily(monkeypatch):
    package = importlib.import_module("routes")
    route_modules = [
        "routes.achievements.routes",
        "routes.admin",
        "routes.games.routes",
    ]
    imported_modules = []
    original_import = builtins.__import__

    def track_route_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in route_modules:
            imported_modules.append(name)
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", track_route_import)
    importlib.reload(package)

    assert imported_modules == []

    router = package.router

    assert isinstance(router, APIRouter)
    assert imported_modules == route_modules
    app = FastAPI()
    app.include_router(router)
    assert set(app.openapi()["paths"]) >= {
        "/users",
        "/games",
        "/games/{game_id}",
    }


def test_root_route_package_rejects_unknown_exports():
    package = importlib.import_module("routes")

    with pytest.raises(AttributeError) as exc_info:
        package.unknown_export

    assert str(exc_info.value) == "unknown_export"


def test_current_user_profile_returns_username_and_role():
    package = importlib.import_module("routes")
    from backend.auth.auth import Principal

    assert package.get_current_user_profile(Principal("alice", "viewer")) == {
        "username": "alice",
        "role": "viewer",
    }
