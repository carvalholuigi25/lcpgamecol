# LCP Game Collection

A FastAPI application for managing and exploring a video game collection. It includes a SQLite-backed API, a browser-based games library and administrator dashboard, and optional IGDB integration for game searches and upcoming releases.

## Requirements

- Python and Node.js with npm
- IGDB/Twitch API credentials only if you want to use IGDB-powered features

## Setup

From the project folder, create and activate a Python environment, install the Python packages, and install the Node.js packages:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install "msgpack>=1.2.3"
npm install
```

The second `pip install` replaces the vulnerable `msgpack` version that `signalrcore` pins. pip then reports that `signalrcore` requires `msgpack==1.1.2`; the test that uses `signalrcore` still passes, so you can ignore the warning.

The security audit (`npm run security`) also needs Semgrep. Semgrep pins vulnerable versions of `mcp` and `opentelemetry-api`, so install it in its own environment instead of the project's:

```powershell
uv tool install semgrep==1.182.1
```

Create your local configuration from the example:

```powershell
Copy-Item config_sample.env.txt config.env
```

Edit `config.env` before starting the app:

- Replace the sample passwords in `AUTH_USERS` with strong, unique passwords. This setting takes precedence over `AUTH_USERNAME` and `AUTH_PASSWORD`.
- Set `JWT_SECRET` to a long, random secret. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"` and paste the output into the file.
- For local HTTP development, set `AUTH_COOKIE_SECURE=false`. Set it to `true` when serving the app over HTTPS.
- Set `IGDB_CLIENT_ID` and `IGDB_CLIENT_SECRET` if you want to use IGDB features.

`config.env` is local configuration and is ignored by Git. Do not commit it or share its credentials.

## Run

Start the app from the project folder:

```powershell
npm start
```

This builds the CSS and starts the development server with `config.env`. To start the server without rebuilding CSS:

```powershell
npm run startapp
```

The app is available at:

- Games library: <http://127.0.0.1:8000/library>
- Upcoming releases: <http://127.0.0.1:8000/library/releases>
- Your profile (any signed-in user): <http://127.0.0.1:8000/profile>
- Feedback (any signed-in user; administrators also answer it here): <http://127.0.0.1:8000/feedback>
- Reset a forgotten password: <http://127.0.0.1:8000/reset-password>
- Administrator dashboard: <http://127.0.0.1:8000/admin>
- Special features (admin tools such as file upload): <http://127.0.0.1:8000/admin/special-features>
- Interactive API docs (Swagger UI): <http://127.0.0.1:8000/docs>
- ReDoc API docs: <http://127.0.0.1:8000/redocs>
- Health check: <http://127.0.0.1:8000/health>

The database is created at `backend/database/mydb.db`. Pending migrations are applied automatically when the app starts.
After initializing the database, seed the default games and achievements with:

```powershell
python -c "from backend.database.database import seed_database; seed_database()"
```

The seed data is defined in `backend/database/seed.sql`; running the seeder more than once does not add duplicates.

## Features

- Create, browse, search, update, and delete games and achievements through the API.
- Browse and search the game library, view release information, and manage collection data through the browser pages.
- Review collection statistics in the administrator dashboard. Dashboard data and write operations require the `admin` role.
- Move between pages with the sidebar, on every page once you're signed in. Its **Activity** group at the top has notifications, messages, and feedback; administrators also see the dashboard and tools groups. The menu button shows or hides it; on wide screens it collapses to icons, and on small screens it opens as an overlay.
- Upload images and PDFs safely from the Special features page (admin only).
- Create a viewer account from the library or dashboard sign-in panel.
- Add games to your own wishlist and favorites from the game details. Administrators also get **Edit** and **Delete** buttons there.
- See changes as they happen: the library and dashboard update by themselves through a SignalR hub at `/hubs/library`. Python clients can subscribe with `signalrcore`; run a single server worker, because live connections are kept in memory.
- Send feedback from the feedback page. Administrators are notified, can set its status and reply, and replies are emailed to users who added an address to their profile.
- Get notifications (bell) and direct messages (envelope) at the top of the sidebar on every page, with live unread counts. Messages to users with an email address are also emailed.
- View game screenshots in an image gallery and save dashboard preferences in the browser.
- Use the library and dashboard in English, Portuguese, German, or French.
- Receive custom HTML error pages for common HTTP errors; API clients retain API-style error responses.
- Optionally search IGDB and view upcoming game releases by configuring IGDB credentials.

## Authentication and roles

API routes require authentication. `POST /auth/token` accepts form fields named `username` and `password`. Its response includes an access token and a refresh token; the access token can be sent as `Authorization: Bearer <access-token>`. Browser sign-in also uses an `HttpOnly` cookie.

By default, `AUTH_USERNAME` and `AUTH_PASSWORD` configure a single administrator account. To configure multiple accounts, set `AUTH_USERS` as a comma-separated list of `username:password:role` entries:

```text
AUTH_USERS=admin:use-a-strong-password:admin,readonly:another-strong-password:viewer
```

Instead of a plaintext password, you can use a password hash in `AUTH_USERS` or `AUTH_PASSWORD`. Generate one with:

```powershell
python -m backend.auth.users hash
```

Both `admin` and `viewer` accounts can read games and achievements. Only `admin` accounts can create, update, or delete records and access administrator data. If `AUTH_USERS` is set, it is used instead of `AUTH_USERNAME` and `AUTH_PASSWORD`.

### Registration

People can create their own accounts from the sign-in panel, or with `POST /auth/register` and a JSON body of `{"username": "...", "password": "..."}`. New accounts always get the `viewer` role and are stored in the `users` table with salted scrypt password hashes. Registration rules:

- Usernames are 3 to 32 characters long, using letters, numbers, dots, hyphens, or underscores, and must start with a letter or number. Usernames are not case-sensitive and cannot match a configured account.
- Passwords must be at least `PASSWORD_MIN_LENGTH` characters long (12 by default) and no longer than 128 characters. They must mix letters with numbers, spaces, or symbols, must not contain the username, and are rejected if they are common or predictable.
- Each client IP can make up to `REGISTRATION_MAX_PER_CLIENT` registration attempts per `REGISTRATION_WINDOW_SECONDS` window (5 per hour by default).
- Set `AUTH_REGISTRATION_ENABLED=false` to turn registration off.

### Two-step sign-in

Any signed-in user can turn on two-step sign-in in **My profile → Security** and choose how to get codes:

- **Authenticator app** (TOTP, RFC 6238): scan the QR code with Google Authenticator, Microsoft Authenticator, 1Password, Authy, or a similar app. Works without email.
- **Email code**: a 6-digit code is emailed at each sign-in. Needs an email address on the profile and email set up on the server (see **Email**).

Turning it on shows 10 one-time recovery codes, for when the phone or mailbox is unavailable. Turning it off, or making new recovery codes, asks for the password again.

With two-step sign-in on, `POST /auth/token` answers `{"two_factor_required": true, "challenge_token": "...", "method": "totp" | "email"}` instead of tokens. Send the code (or a recovery code) with the challenge to `POST /auth/two-factor/verify` to get the tokens and cookie; `POST /auth/two-factor/resend` emails a new code. A challenge lasts 10 minutes and allows 5 wrong codes. An administrator can turn it off for a user who lost both their device and their recovery codes, from the user directory.

### Forgotten passwords

The **Forgot your password?** link on the sign-in panels opens `/reset-password`. People enter their username or email, and get a one-time link by email (when their profile has an address). The answer is the same whether or not the account exists. Links expire after `PASSWORD_RESET_TTL_SECONDS` (1 hour by default), and each client can ask `PASSWORD_RESET_MAX_PER_CLIENT` times per `PASSWORD_RESET_WINDOW_SECONDS` (5 per hour by default). Only a hash of each link is stored.

Administrators can also create a link from the user directory (**Account access → Create reset link**) and pass it on themselves. Setting a new password signs the account out everywhere: access and refresh tokens issued earlier stop working. Accounts configured in `AUTH_USERS` change their password in the server settings instead.

### Session security

Failed sign-ins lock a username for each client after `LOGIN_MAX_ATTEMPTS` attempts (3 by default) for `LOGIN_LOCKOUT_SECONDS` seconds. Usernames are not case-sensitive for this lockout. While a username is locked, its password is not checked. Unknown usernames take as long to check as real ones, so response times do not reveal which accounts exist.

When a request is authenticated by the browser cookie, the server rejects state-changing requests (anything other than `GET`, `HEAD`, or `OPTIONS`) whose `Origin` or `Referer` header comes from a site other than the app or a `CORS_ORIGINS` entry. Responses under `/auth/` are sent with `Cache-Control: no-store`. If `JWT_SECRET` is missing, the app signs tokens with a random secret generated at startup (so sessions end on every restart) and logs a warning; it also warns when the secret is shorter than 32 characters.

Access tokens expire after 30 minutes by default. Refresh tokens expire after 7 days. Set `TOKEN_EXPIRE_SECONDS` and `REFRESH_TOKEN_EXPIRE_SECONDS` to change those durations. Exchange a valid refresh token at `POST /auth/refresh`, and use `POST /auth/logout` to clear the browser's authentication cookie.

Requests are limited to 60 per client IP per 60 seconds by default. Set `RATE_LIMIT_REQUESTS` and `RATE_LIMIT_WINDOW_SECONDS` to change these limits. Rejected requests receive `429 Too Many Requests` and a `Retry-After` header.

The default CORS origins are `http://localhost:3000` and `http://127.0.0.1:3000`. Set `CORS_ORIGINS` to a comma-separated list of trusted origins to change them.

## API overview

The interactive API documentation at `/docs` lists all routes and their request/response schemas. Common routes include:

| Method | Route | Description |
| --- | --- | --- |
| `POST` | `/auth/token` | Sign in and obtain access and refresh tokens |
| `POST` | `/auth/register` | Create a viewer account |
| `POST` | `/auth/refresh` | Exchange a refresh token for an access token |
| `POST` | `/auth/logout` | Clear the authenticated browser session |
| `GET` | `/users` | Get the signed-in user's profile |
| `GET` | `/admin/users` | List every account with its profile and favorite games (admin only) |
| `GET` | `/admin/users/{username}` | Get one user's profile (admin only) |
| `PUT` | `/admin/users/{username}` | Update a user's display name, bio, location, avatar, cover, and favorite games (admin only) |
| `GET` | `/games` | List games; supports `skip` and `limit` |
| `GET` | `/games/page` | List a page of games with the total count |
| `GET` | `/games/search` | Search games by title, genre, platform, or release year |
| `GET` | `/games/{game_id}` | Get a game |
| `POST` | `/games` | Create a game (admin only) |
| `PUT` | `/games/{game_id}` | Update a game (admin only) |
| `DELETE` | `/games/{game_id}` | Delete a game (admin only) |
| `GET` | `/games/next-releases` | Get upcoming IGDB releases |
| `GET` | `/games/external-search` | Search for games outside the local collection |
| `GET` | `/games/{game_id}/achievements` | List a game's achievements |
| `POST` | `/games/{game_id}/achievements` | Create an achievement (admin only) |
| `GET` | `/admin/uploads` | List uploaded files (admin only) |
| `POST` | `/admin/uploads` | Upload a file as multipart form field `file` (admin only) |
| `GET` | `/admin/uploads/limits` | Get the upload size limit and allowed file types (admin only) |
| `GET` | `/admin/uploads/{upload_id}` | Download an uploaded file; add `?inline=true` to preview an image (admin only) |
| `DELETE` | `/admin/uploads/{upload_id}` | Delete an uploaded file (admin only) |

The game create/update body uses fields such as `title`, `genre`, `platforms`, and `release_year`. Optional fields include `minimum_system_requirements`, `recommended_system_requirements`, `developer_name`, `publisher_name`, `website_url`, `trailer_url`, and `screenshots` (an array of image URLs). For the complete schema and all routes, use `/docs`.

List endpoints that support pagination use zero-based `skip` and `limit` parameters. For example, `/games?skip=10&limit=10` returns the second page of games. The default `skip` is `0`; `limit` defaults to `10` and must be between `1` and `100`.

## Safe file uploads

Administrators can upload PNG, JPEG, GIF, WebP, and PDF files from the Special features page or the `/admin/uploads` API. Uploads are protected as follows:

- A file is accepted only if its contents begin with the signature of an allowed type and its extension matches that type. The filename and the `Content-Type` sent by the client are not trusted. SVG, HTML, and other active content are refused.
- Request bodies larger than the limit are rejected before they are parsed, and file data is counted as it is received. The default limit is 5 MB; change it with `UPLOAD_MAX_BYTES`. `UPLOAD_MAX_FILES` limits the number of stored files (500 by default).
- Files are stored in `uploads/` by default, outside the public static folders, under random names. Set `UPLOAD_DIRECTORY` to use another folder. Original filenames are cleaned of path segments and control characters, and they are used only as display and download names.
- Downloads are sent as attachments with `Content-Security-Policy: default-src 'none'; img-src 'self'; sandbox`, `X-Content-Type-Options: nosniff`, and `Cache-Control: private, no-store`. Only images can be previewed inline.

The `uploads/` folder is ignored by Git.

## Database migrations

The `Game` and `Achievement` Pydantic models define the database schema. After changing a model, generate a migration and review the resulting SQL:

```powershell
npm run db:make -- -n add_game_tags
npm run db:make -- --rename games.hoursplayed=hours_played
npm run db:make -- --allow-drop
```

Use `--allow-drop` when removing a field. Commit the generated migration with your model changes. Then check or apply migrations with:

```powershell
npm run db:check
npm run db:status
npm run db:migrate
```

New required fields need a default so existing rows can be migrated. Changes to field types, defaults, or optionality rebuild the affected table while preserving existing rows. When enum values are removed, review and apply any data updates called out in the generated migration.

## Email

Email is optional; without it, replies and messages are only shown in the app. Set these in `config.env`:

| Setting | Meaning |
| --- | --- |
| `SMTP_HOST`, `SMTP_PORT` | Mail server (port 587 by default). |
| `SMTP_SECURITY` | `starttls` (default), `ssl` (usually port 465), or `none` for a local relay. |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | Sign-in for the mail server, if it needs one. |
| `MAIL_FROM` | Sender, for example `lcpgamecol <no-reply@example.com>`. |
| `APP_BASE_URL` | Address used for links in emails (default `http://127.0.0.1:8000`). |
| `MAIL_OUTBOX_DIR` | With no `SMTP_HOST`, write each email to this folder as an `.eml` file instead. Useful while developing. |

Users only get email when their profile has an address (**My profile → Edit profile → Email for notifications**).

## Audit reports

`npm run lighthouse` and `npm run security` write their results to `tests/reports/<lighthouse|security>/<timestamp>/`, including a `report.html` page for the run, and update `tests/reports/index.html`, which lists every run with score and findings trends. To rebuild the pages from existing results:

```powershell
npm run audit-report          # every run, then open tests/reports/index.html
npm run audit-report -- --kind security --run 20261028-095205 --open
```

Pass `--no-html` to either audit script to skip the pages.

## Tests and coverage

Run the test suite:

```powershell
npm test
```

Tests use a temporary SQLite database and do not modify `backend/database/mydb.db`. To run tests and generate a coverage report:

```powershell
npm run coverage
```

The HTML report is written to `mycoverage/htmlcov/index.html`. To generate the project's formatted coverage output and HTML report, run:

```powershell
python .\mycoverage\coverage_report.py --html
```
