# Games CRUD API

A simple FastAPI CRUD API backed by SQLite.

## Setup

From this folder, create or activate a Python environment and install the dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Run

```powershell
uvicorn main:app --reload
```

Open the interactive API documentation at http://127.0.0.1:8000/docs or the ReDoc documentation at http://127.0.0.1:8000/redoc.

Open the games page at http://127.0.0.1:8000/library or upcoming releases at http://127.0.0.1:8000/library/releases. Sign in with the configured API credentials to view and search the collection.

Open the administrator dashboard at http://127.0.0.1:8000/admin for collection statistics and charts. Dashboard data is restricted to administrator accounts. The original `/pages/...` URLs remain available.

Custom browser error pages are available for HTTP 400, 401, 403, 404, 429, and 500 responses. They are served automatically to requests that accept HTML; API clients continue to receive the existing error response format. The standalone pages are available at `/pages/errors/{status}.html`.

Dashboard preferences, including whether the collection records panel is expanded and which records tab is selected, are saved in the browser and restored when the dashboard is reopened.

The games pages and administrator dashboard support English, Portuguese, German, and French. Use the Language selector in the page header; your choice is saved in the browser and shared between pages.

The SQLite database is created automatically as `backend/database/mydb.db` when the app starts.

## Database migrations

The Pydantic models (`Game` and `Achievement`) define the database tables. After changing a model, generate a migration:

```powershell
npm run db:make -- -n add_game_tags                              # writes backend/database/migrations/0001_add_game_tags.sql
npm run db:make -- --rename games.hoursplayed=hours_played       # a renamed field keeps its data
npm run db:make -- --allow-drop                                  # required when a field is removed
```

Check the generated SQL and keep it with your code. Pending migrations are applied when the app starts, or by running `npm run db:migrate`. Use `npm run db:status` to see which migrations are applied. `npm run db:check` and the test suite both fail if a model changed without a migration.

New required fields must have a default, because existing rows need a value. When a field's type, default or optional/required setting changes, the migration rebuilds the table and copies the existing rows over. When enum values are removed, the migration includes a commented-out `UPDATE` for any rows that still use them.

## Tests and coverage

Install the test dependencies from `requirements.txt`, then run:

```powershell
python .\mycoverage\coverage_report.py --html
```

The test suite uses a temporary SQLite database, so it does not modify `mydb.db`.

Open the generated coverage report in your browser:

```powershell
Start-Process .\mycoverage\htmlcov\index.html
```

Coverage configuration, scripts, and generated reports are kept in `mycoverage/`. The HTML report is regenerated in `mycoverage/htmlcov/` each time the coverage command runs.

## Authentication and rate limits

CRUD endpoints require a bearer token. Set these environment variables before starting the API:

```powershell
$env:AUTH_USERNAME = "admin"
$env:AUTH_PASSWORD = "use-a-strong-password"
$env:JWT_SECRET = "use-a-long-random-secret"
```

Browser clients from `http://localhost:3000` and `http://127.0.0.1:3000` are allowed by CORS by default. Set `CORS_ORIGINS` to a comma-separated list of trusted origins to change this policy, for example:

```powershell
$env:CORS_ORIGINS = "https://games.example.com,https://admin.example.com"
```

The API also sends browser security policy headers including `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and `Permissions-Policy`.

Request tokens with `POST /auth/token` using form fields `username` and `password`. The response includes an access token and a refresh token. Send the access token on protected requests as `Authorization: Bearer <token>`. Access tokens expire after 30 minutes by default; set `TOKEN_EXPIRE_SECONDS` to change that. Refresh tokens expire after 7 days by default; set `REFRESH_TOKEN_EXPIRE_SECONDS` to change that. Send a refresh token as a bearer token to `POST /auth/refresh` to receive a new access token. Call the protected `POST /auth/logout` endpoint to clear the browser's authentication cookie.

Requesting a token also creates an `HttpOnly` `access_token` cookie, so a browser keeps the session across page refreshes. Protected requests can use either this cookie or the bearer header. Set `AUTH_COOKIE_SECURE=true` when serving over HTTPS.

Each client IP is limited to 60 requests per 60 seconds by default. Configure `RATE_LIMIT_REQUESTS` and `RATE_LIMIT_WINDOW_SECONDS` to change the limits. A rejected request returns `429 Too Many Requests` and a `Retry-After` header.

Set `IGDB_CLIENT_ID` and `IGDB_CLIENT_SECRET` to enable `GET /games/next-releases`. The endpoint uses Twitch client-credentials authentication to query IGDB.

## Roles (RBAC)

Every user has one of two roles: `admin` or `viewer`. Both roles can authenticate and read games/achievements data; only `admin` can create, update, or delete games and achievements. A request from a `viewer` to a write endpoint receives `403 Forbidden`.

By default, `AUTH_USERNAME`/`AUTH_PASSWORD` log in as `admin`. To configure multiple users with different roles, set `AUTH_USERS` instead, as a comma-separated list of `username:password:role`:

```powershell
$env:AUTH_USERS = "admin:use-a-strong-password:admin,readonly:another-password:viewer"
```

The signed-in user's role is embedded as a claim in their access token and re-checked on every request.

## Endpoints

- `POST /games` creates a game
- `POST /auth/refresh` exchanges a valid refresh token for a new access token
- `POST /auth/logout` clears the authenticated browser session
- `GET /games` lists games with optional `skip` and `limit` pagination parameters
- `GET /games/covers` lists game cover URLs with optional `skip` and `limit` pagination parameters
- `GET /games/next-releases` lists upcoming games from IGDB, ordered by release date
- `GET /games/external-search` searches IGDB by a query without changing the local collection
- `GET /games/{game_id}` gets one game
- `PUT /games/{game_id}` updates a game
- `DELETE /games/{game_id}` deletes a game
- `DELETE /games/all` deletes all games
- `POST /games/reset-autoincrement` safely recalculates the next game ID (admin only)
- `GET /games/search` searches games with optional `skip` and `limit` pagination parameters
- `POST /achievements/reset-autoincrement` safely recalculates the next achievement ID (admin only)
- `GET /games/{game_id}/achievements` lists a game's achievements with optional `skip` and `limit` pagination parameters
- `POST /games/{game_id}/achievements` creates an achievement for a game

Example JSON body:

```json
{
  "title": "Portal 2",
  "genre": "Puzzle",
  "platforms": "PC",
  "release_year": 2011,
  "minimum_system_requirements": "Windows 7 / Intel Core 2 Duo / 2 GB RAM / DirectX 9 compatible GPU / 8 GB storage",
  "recommended_system_requirements": "Windows 10 / Quad-core CPU / 4 GB RAM / Dedicated GPU / 8 GB storage"
}
```

Minimum and recommended PC system requirements are optional text fields. Existing games without requirement details return `null` for both fields.

Game records can also include `developer_name`, `publisher_name`, `website_url`, and `trailer_url`. The optional `screenshots` field is an array of image URLs used for the game's screenshot gallery. Select a screenshot thumbnail in game details to open the LightGallery viewer, where images can be navigated and zoomed. Existing records without these values remain valid; the administrator dashboard accepts one screenshot URL per line.

Pagination uses zero-based `skip` and `limit` query parameters. `skip` defaults to `0`; `limit` defaults to `10` and must be between `1` and `100`. For example, `GET /games?skip=10&limit=10` returns the second page of games.
