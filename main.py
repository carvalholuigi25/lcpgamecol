import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, Depends, FastAPI, Request, Response
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette import status
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import FileResponse, HTMLResponse, PlainTextResponse

from backend.access.middleware import AccessControlMiddleware
from backend.auth import two_factor
from backend.auth.auth import (
    AUTH_COOKIE_NAME,
    AUTH_COOKIE_SECURE,
    TOKEN_EXPIRE_SECONDS,
    authenticate,
    create_access_token,
    get_current_user,
    get_current_user_from_refresh_token,
    get_role_for_username,
    get_trusted_origins,
    issue_session,
    register_user,
)
from backend.auth.rate_limit import RateLimitMiddleware
from backend.auth.routes import router as account_router
from backend.database.database import initialize_database
from backend.realtime.hub import router as realtime_router
from error_pages.error_pages import ERROR_PAGE_FILES, accepts_html, error_page_response
from routes import router
from routes.admin.uploads import UploadBodyLimitMiddleware

PAGES_DIRECTORY = Path(__file__).parent / "pages"
# Vendor packages only change on `npm install`; app assets change while developing,
# so their lifetime is configurable (set STATIC_CACHE_MAX_AGE=0 to always revalidate).
VENDOR_CACHE_MAX_AGE = 7 * 24 * 60 * 60
STATIC_CACHE_MAX_AGE = int(os.getenv("STATIC_CACHE_MAX_AGE", "3600"))


class CachedStaticFiles(StaticFiles):
    def __init__(self, *args, max_age: int, **kwargs):
        super().__init__(*args, **kwargs)
        self.cache_control = f"public, max-age={max_age}" if max_age > 0 else "no-cache"

    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers.setdefault("Cache-Control", self.cache_control)
        return response


def _get_cors_origins() -> list[str]:
    return get_trusted_origins()


class RegistrationRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class SecurityPolicyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        if request.url.scheme == "https":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        if request.url.path.startswith("/auth/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="lcpgamecol API",
    description="Explore and manage your game collection through the lcpgamecol API.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url="/redocs",
    swagger_ui_parameters={
        "deepLinking": True,
        "displayRequestDuration": True,
        "filter": True,
        "persistAuthorization": True,
        "tryItOutEnabled": False,
    },
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityPolicyMiddleware)
app.add_middleware(UploadBodyLimitMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)
# Runs after the rate limit (added last, so outermost) so blocked visitors are rate limited too.
app.add_middleware(AccessControlMiddleware)
app.add_middleware(RateLimitMiddleware)
app.mount(
    "/nmodules",
    CachedStaticFiles(
        directory=Path(__file__).parent / "node_modules", max_age=VENDOR_CACHE_MAX_AGE
    ),
    name="/nmodules",
)
app.mount(
    "/static",
    CachedStaticFiles(
        directory=Path(__file__).parent / "static", max_age=STATIC_CACHE_MAX_AGE
    ),
    name="static",
)
app.mount(
    "/public",
    CachedStaticFiles(
        directory=Path(__file__).parent / "public", max_age=STATIC_CACHE_MAX_AGE
    ),
    name="public",
)
app.mount(
    "/pages",
    StaticFiles(directory=PAGES_DIRECTORY, html=True),
    name="pages",
)


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(
    request: Request, exc: StarletteHTTPException
) -> Response:
    if exc.status_code in ERROR_PAGE_FILES and accepts_html(
        request.headers.get("accept", "")
    ):
        return error_page_response(exc.status_code, headers=exc.headers)
    return await http_exception_handler(request, exc)


@app.exception_handler(Exception)
async def handle_unexpected_exception(request: Request, _exc: Exception) -> Response:
    if accepts_html(request.headers.get("accept", "")):
        return error_page_response(status.HTTP_500_INTERNAL_SERVER_ERROR)
    return PlainTextResponse(
        "Internal Server Error", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
    )


@app.get("/docs", include_in_schema=False)
def swagger_ui():
        swagger_page = get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - Swagger UI",
        swagger_ui_parameters=app.swagger_ui_parameters,
        swagger_css_url="/public/styles/css/swagger.css",
    )
        bootstrap_css = (
            '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@6.0.0-alpha.1/dist/css/bootstrap.min.css">'
        )
        bootstrap_js = (
            '<script src="https://cdn.jsdelivr.net/npm/bootstrap@6.0.0-alpha.1/dist/js/bootstrap.bundle.min.js"></script>'
        )
        header = """
        <header class="api-docs-header bg-dark text-white">
            <div class="container py-3 d-flex align-items-center justify-content-between">
                <div>
                    <div class="h5 mb-1">Games API</div>
                    <div class="small text-white-50">Interactive API reference</div>
                </div>
                <div class="api-docs-tools">
                    <label class="visually-hidden" for="swagger-theme">Swagger UI theme</label>
                    <select id="swagger-theme" class="form-select form-select-sm" aria-label="Swagger UI theme">
                        <option value="white">White</option>
                        <option value="dark">Dark</option>
                        <option value="auto">Auto</option>
                        <option value="sunsetvibes">Sunset Vibes</option>
                        <option value="cyber-retro">Cyber Retro Gaming</option>
                        <option value="rgb">RGB</option>
                    </select>
                    <span class="badge rounded-pill text-bg-info">v1.0.0</span>
                </div>
            </div>
        </header>
        """
        theme_script = """
        <script>
            (() => {
                const storageKey = "games-api-swagger-theme";
                const selector = document.getElementById("swagger-theme");
                const savedTheme = localStorage.getItem(storageKey) || "auto";

                document.body.dataset.theme = savedTheme;
                selector.value = savedTheme;
                selector.addEventListener("change", (event) => {
                    const theme = event.target.value;
                    document.body.dataset.theme = theme;
                    localStorage.setItem(storageKey, theme);
                });
            })();
        </script>
        """
        content = swagger_page.body.decode("utf-8")
        content = content.replace("</head>", f"{bootstrap_css}</head>")
        content = content.replace("</body>", f"{bootstrap_js}</body>")
        content = content.replace("<body>", f"<body>{header}{theme_script}")
        return HTMLResponse(content=content)


@app.post("/auth/token", tags=["authentication"])
def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    response: Response,
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict:
    """Sign in. With two-factor sign-in on, this returns a challenge instead of tokens;
    finish with POST /auth/two-factor/verify."""
    client_id = request.client.host if request.client else "unknown"
    principal = authenticate(form_data, client_id)
    method = two_factor.enabled_method(principal.username)
    if method and two_factor.skip_for_development(principal.username):
        method = None
    if method:
        challenge, code = two_factor.create_challenge(principal, method)
        if code:
            background_tasks.add_task(two_factor.send_challenge_code, principal.username, code)
        return challenge
    return issue_session(response, principal)


@app.post("/auth/register", status_code=201, tags=["authentication"])
def register(body: RegistrationRequest, request: Request) -> dict[str, str]:
    client_id = request.client.host if request.client else "unknown"
    principal = register_user(body.username, body.password, client_id)
    return {"username": principal.username, "role": principal.role}


@app.post("/auth/refresh", tags=["authentication"])
def refresh(
    response: Response,
    username: str = Depends(get_current_user_from_refresh_token),
) -> dict[str, str]:
    token = create_access_token(username, get_role_for_username(username))
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        max_age=TOKEN_EXPIRE_SECONDS,
        httponly=True,
        secure=AUTH_COOKIE_SECURE,
        samesite="lax",
    )
    return {"access_token": token, "token_type": "bearer"}


@app.post("/auth/logout", status_code=204, tags=["authentication"])
def logout(
    response: Response,
    _username: str = Depends(get_current_user),
) -> None:
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        secure=AUTH_COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )


@app.get("/")
def read_root():
    return RedirectResponse(url="/library", status_code=status.HTTP_302_FOUND)

@app.get("/favicon.ico", include_in_schema=False)
def read_favicon() -> FileResponse:
    return FileResponse(
        Path(__file__).parent / "public" / "images" / "favicon.svg",
        media_type="image/svg+xml",
        headers={"Cache-Control": f"public, max-age={VENDOR_CACHE_MAX_AGE}"},
    )


@app.get("/pages")
def read_pages():
    return RedirectResponse(url="/library", status_code=status.HTTP_302_FOUND)


@app.get("/library", include_in_schema=False)
def read_games_page() -> FileResponse:
    return FileResponse(PAGES_DIRECTORY / "games" / "games.html", media_type="text/html")


@app.get("/library/releases", include_in_schema=False)
def read_games_releases_page() -> FileResponse:
    return FileResponse(
        PAGES_DIRECTORY / "games" / "games_releases.html", media_type="text/html"
    )


@app.get("/profile", include_in_schema=False)
def read_profile_page() -> FileResponse:
    return FileResponse(PAGES_DIRECTORY / "users" / "profile.html", media_type="text/html")


@app.get("/reset-password", include_in_schema=False)
def read_reset_password_page() -> FileResponse:
    return FileResponse(PAGES_DIRECTORY / "users" / "reset_password.html", media_type="text/html")


@app.get("/feedback", include_in_schema=False)
def read_feedback_page() -> FileResponse:
    return FileResponse(PAGES_DIRECTORY / "users" / "feedback.html", media_type="text/html")


@app.get("/admin", include_in_schema=False)
def read_admin_page() -> FileResponse:
    return FileResponse(PAGES_DIRECTORY / "admin" / "admin.html", media_type="text/html")

@app.get("/admin/special-features", include_in_schema=False)
def read_special_features_page() -> FileResponse:
    return FileResponse(
        PAGES_DIRECTORY / "admin" / "special_features.html", media_type="text/html"
    )


@app.get("/admin/moderation", include_in_schema=False)
def read_moderation_page() -> FileResponse:
    return FileResponse(PAGES_DIRECTORY / "admin" / "moderation.html", media_type="text/html")


@app.get("/admin/user-directory", include_in_schema=False)
def read_users_page() -> FileResponse:
    return FileResponse(PAGES_DIRECTORY / "admin" / "users.html", media_type="text/html")


@app.get("/health", tags=["health"])
def read_health_root(_username: str = Depends(get_current_user)) -> dict[str, str]:
    return {"message": "Games API is running"}

app.include_router(router)
app.include_router(realtime_router)
app.include_router(account_router)
