import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Request, Response
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from starlette import status
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import FileResponse, HTMLResponse, PlainTextResponse

from backend.auth.auth import (
    AUTH_COOKIE_NAME,
    AUTH_COOKIE_SECURE,
    TOKEN_EXPIRE_SECONDS,
    authenticate,
    create_access_token,
    create_refresh_token,
    get_current_user,
    get_current_user_from_refresh_token,
    get_role_for_username,
)
from backend.auth.rate_limit import RateLimitMiddleware
from backend.database.database import initialize_database
from error_pages.error_pages import ERROR_PAGE_FILES, accepts_html, error_page_response
from routes import router

PAGES_DIRECTORY = Path(__file__).parent / "pages"


def _get_cors_origins() -> list[str]:
    return [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
        ).split(",")
        if origin.strip()
    ]


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
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains",
                "Cache-Control", "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0"
            )
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="Games API",
    description="Explore and manage your game collection through the Games API.",
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
app.add_middleware(RateLimitMiddleware)
app.mount(
    "/nmodules",
    StaticFiles(directory=Path(__file__).parent / "node_modules"),
    name="/nmodules",
)
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent / "static"),
    name="static",
)
app.mount(
    "/public",
    StaticFiles(directory=Path(__file__).parent / "public"),
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
) -> dict[str, str]:
    client_id = request.client.host if request.client else "unknown"
    principal = authenticate(form_data, client_id)
    token = create_access_token(principal.username, principal.role)
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        max_age=TOKEN_EXPIRE_SECONDS,
        httponly=True,
        secure=AUTH_COOKIE_SECURE,
        samesite="lax",
    )
    return {
        "access_token": token,
        "refresh_token": create_refresh_token(principal.username),
        "token_type": "bearer",
    }


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


@app.get("/admin", include_in_schema=False)
def read_admin_page() -> FileResponse:
    return FileResponse(PAGES_DIRECTORY / "admin" / "admin.html", media_type="text/html")

@app.get("/health", tags=["health"])
def read_health_root(_username: str = Depends(get_current_user)) -> dict[str, str]:
    return {"message": "Games API is running"}

app.include_router(router)
