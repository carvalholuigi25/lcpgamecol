# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **Reviews** and **Comments** sections in the game details, on the library and upcoming releases pages.
  - Every signed-in user can leave one review per game, with 1 to 5 stars and optional text (up to 2,000 characters). Posting again updates it. The section shows the average rating and the number of reviews.
  - Comments are free-form (up to 1,000 characters each), newest first.
  - Authors can delete their own reviews and comments; administrators can delete anyone's.
  - On the releases page, reviewing or commenting first copies the release into the library, like **Add to wishlist**.
  - Both sections update live (new events `reviewsChanged` and `commentsChanged`). Deleting a game deletes its reviews and comments.
  - New endpoints: `GET /games/{game_id}/reviews`, `PUT /games/{game_id}/reviews/mine`, `DELETE /games/{game_id}/reviews/{review_id}`, `GET`/`POST /games/{game_id}/comments`, and `DELETE /games/{game_id}/comments/{comment_id}`.
- Italian, Spanish, and Japanese translations for every page. Pick them from the **Language** menu; dates and times follow the chosen language.
- An **Access control** panel on the Special features page, with an on/off switch for each rule. See **Access control** in the README.
  - **Geoblock**: block the listed countries, or allow only the listed countries, and optionally block visitors whose country cannot be found.
  - **VPN checker**: block visitors using a VPN, proxy, or Tor, and optionally hosting providers and data centres. **Check an address** shows the country, VPN and hosting status of any address and whether the current rules would let it in.
  - **Scheduled lockdown**: close the library every week on chosen days and times, or once between two dates, in a chosen time zone, with an optional message for visitors.
  - Blocked visitors see a page that says why (`403`, or `503` with `Retry-After` during a lockdown); API clients get a `reason` field. The panel lists the last 50 blocked requests.
  - Administrators are never blocked, and the dashboard sign-in always stays open.
  - Countries and VPNs are looked up with ip-api.com by default and cached. New settings: `ACCESS_CONTROL_DISABLED`, `ACCESS_CONTROL_TRUST_PROXY`, `GEOIP_COUNTRY_HEADER`, `IP_LOOKUP_URL`, `IP_LOOKUP_TIMEOUT_SECONDS`, and `IP_LOOKUP_CACHE_SECONDS`.
  - New endpoints: `GET`/`PUT /admin/access-control` and `GET /admin/access-control/check-ip`.
  - New dependency: `tzdata`, for time zones on Windows.
- Two-step sign-in for every account, set up in **My profile → Security**. Choose an authenticator app (scan a QR code) or codes sent by email, and get 10 one-time recovery codes.
  - Sign-in asks for the code after the password, on the library, releases and dashboard sign-in panels. You can also enter a recovery code or, for email, ask for a new code.
  - Turning it off or making new recovery codes asks for the password again. Administrators can turn it off for a user from the user directory.
  - `POST /auth/token` now answers `{"two_factor_required": true, "challenge_token": ..., "method": ...}` for these accounts. Finish with `POST /auth/two-factor/verify` (`POST /auth/two-factor/resend` emails a new code).
  - New endpoints: `GET /users/me/two-factor`, and `POST` on `/users/me/two-factor/setup`, `/enable`, `/disable` and `/recovery-codes`, plus `DELETE /admin/users/{username}/two-factor`.
  - New dependency: `segno`, for the QR code.
- A **Forgot your password?** page at `/reset-password`, linked from every sign-in panel. It emails a one-time link (valid for 1 hour) to the address on the profile.
  - Administrators can create a link from the user directory, for users without an email address.
  - Changing the password with a link signs the account out everywhere, and the user gets a notification and an email about it.
  - New endpoints: `POST /auth/password-reset/request`, `GET /auth/password-reset/check`, `POST /auth/password-reset/confirm`, and `POST /admin/users/{username}/password-reset`.
  - New settings: `PASSWORD_RESET_TTL_SECONDS`, `PASSWORD_RESET_MAX_PER_CLIENT`, and `PASSWORD_RESET_WINDOW_SECONDS`.
- The user directory shows whether each user has two-step sign-in on (`two_factor_enabled` in `/admin/users`).
- A **Feedback** page at `/feedback` for every signed-in user, linked from the library, the releases page, the profile page, and the administrator sidebar.
  - Send a bug report, idea, question, praise, or other feedback, optionally with the page it is about, and follow its status and replies.
  - Administrators get an **All feedback** panel (`/feedback#manage`) to filter by status, change the status, reply, and delete. New feedback notifies every administrator.
  - Replies notify the user and are emailed to them when their profile has an email address. The panel shows whether each reply was emailed.
  - New endpoints: `POST /feedback`, `GET /feedback/mine`, and for administrators `GET /admin/feedback`, `PUT` and `DELETE` on `/admin/feedback/{feedback_id}`.
- Notifications and messages buttons at the top of the sidebar on every page, with unread badges that update live.
  - The bell lists notifications (feedback replies and status changes, new messages, and new feedback for administrators). Open one to go where it points, delete it, or mark all as read.
  - The envelope opens your inbox and sent messages. Write to any account, read, reply, and delete; a deleted message disappears only for you.
  - Links such as `/profile?inbox=messages` open the dialog directly; emails use them.
  - New endpoints: `GET /notifications`, `POST /notifications/read-all`, `POST /notifications/{id}/read`, `DELETE /notifications/{id}`, `GET`/`POST /messages`, `GET /messages/recipients`, `POST /messages/{id}/read`, and `DELETE /messages/{id}`.
  - New live events: `notificationsChanged` and `messagesChanged` (sent only to their owner) and `feedbackChanged`.
- Optional email over SMTP (`SMTP_HOST` and related settings), or to `.eml` files in `MAIL_OUTBOX_DIR` while developing. See **Email** in the README.
- An **Email for notifications** field on your profile. `PUT /users/me/profile` and `PUT /admin/users/{username}` accept `email`; leaving it out keeps the current address.
- `scripts/audit_report.py` (`npm run audit-report`) turns Lighthouse and security audit results into HTML pages: one per run and an index of every run with trends. Both audit scripts now write these pages after each run (`--no-html` to skip). Lighthouse summaries now also store the score of every audited category.
- Game details in the library now have **Add to wishlist** and **Add to favorites** buttons for every signed-in user, and **Edit** and **Delete** buttons for administrators.
  - Wishlists and favorites are kept per user. Favorites are the same list administrators see in the user directory (up to 12 games).
  - **Edit** opens the administrator dashboard with that game ready to edit (`/admin?edit-game=<id>`).
  - The four buttons are round icon buttons. Their labels appear as tooltips (`title`) and are read by screen readers (`aria-label`).
  - Game cards show a heart or bookmark badge when the game is in your favorites or on your wishlist.
- The upcoming releases page has the same four buttons. Releases come from IGDB, so Add to wishlist, Add to favorites, and Edit first copy the release into the library (the server fetches the data from IGDB; importing the same release twice reuses the first copy). Delete appears once a release is in the library and removes only the library copy.
- **Sort by** menus on the library and upcoming releases pages. Your choice is remembered in the browser.
  - Library: first or recently added, title (A–Z or Z–A), newest or oldest releases, highest user or critic rating, and most or least played. Sorting happens on the server, so it applies across all pages, and games with no rating or playtime are listed last.
  - Releases: release date (soonest or latest), most anticipated (IGDB hype), title, and highest user or critic rating.
  - New query parameters `sort` and `order` on `GET /games`, `/games/page`, `/games/search`, and `/games/all-releases`. Without them, the order is the same as before.
- New endpoints for releases: `GET /games/igdb/links?ids=…`, `GET /games/igdb/{igdb_id}`, and `POST /games/igdb/{igdb_id}/import`.
- New endpoints: `GET /users/me/game-lists`, and `PUT`/`DELETE` on `/games/{game_id}/wishlist` and `/games/{game_id}/favorite`.
- Live updates over the SignalR protocol at `/hubs/library` (JSON hub protocol over WebSockets).
  - The library and the administrator dashboard refresh by themselves when games or achievements change, and a **Live** indicator shows the connection state.
  - Events: `gameChanged`, `achievementChanged`, and `listsChanged`, which is sent only to the user who owns the list.
  - The browser uses `@microsoft/signalr`. Python clients can connect with `signalrcore` (now in `requirements.txt`).
- A **My profile** page at `/profile` for every signed-in user, linked from the library, the releases page, and the administrator sidebar.
  - Edit your display name, bio, location, avatar, and cover. It is the same profile administrators see in the user directory.
  - Reorder or remove your favorite games, and see your wishlist with buttons to remove a game or add it to your favorites.
  - The page refreshes by itself when your lists change in another tab.
- New endpoints: `GET` and `PUT` on `/users/me/profile`. Leaving `favorite_game_ids` out of a `PUT` keeps your favorites as they are.
- `TODO.md` and this changelog.

### Changed

- The sidebar is now on every page for every signed-in user, including the library and releases pages. Notifications, Messages and Feedback are at the top, in a new **Activity** group, instead of in the page header. Administrators also see the dashboard and tools links. The links are built by `sidebar.js`, so pages only include an empty `<aside id="admin-sidebar">`.
- When the sidebar is shown, the top bar of the administrator, profile and feedback pages no longer repeats its links.
- `GET /users` now returns the signed-in user's `role` as well as their `username`.
- The **Liquid glass** theme was redesigned for the library and the administrator pages: translucent panels over a slowly moving colour background, light edges on panels, glass-style buttons and inputs, and a see-through details dialog. It falls back to solid panels when the browser can't blur the background or the system asks for reduced transparency, and it stops animating when reduced motion is requested.
- Automatic and live dashboard refreshes no longer discard unsaved changes in the game or achievement forms, and they keep the selected game.

### Fixed

- The administrator top bar no longer overlaps "API" and "Language" on wide screens, and no longer runs off the side of the screen on phones, where the notifications, messages and log out buttons could not be reached.
- On the library pages, the theme menu no longer spills past the right edge of the page.
- On narrow screens, the upcoming releases filter now wraps onto several rows instead of squeezing every field into one.
- Labels in `aria-label`, `title`, `placeholder`, and `alt` attributes that scripts change after the page loads (for example, a button switching between "Add to wishlist" and "Remove from wishlist") are now translated. Before, the translator restored the first label it had seen.
- Release details on the upcoming releases page asked for achievements using the IGDB id. They found nothing, or the achievements of an unrelated library game that happened to have the same id. They now show the achievements of the release's library copy, update live, and explain how to track achievements when the release is not in the library yet.
- Added missing Portuguese, German, and French translations for the library, the administrator dashboard, special features, the user directory, age ratings, screenshots, and toast messages.
- Registration hints shown by the browser ("The passwords do not match." and others) are now translated.
- With the **Auto** theme, the light-mode hover glow on game cards no longer appears in other themes when the system uses a light colour scheme.

### Security

- When `JWT_SECRET` is not set, tokens are now signed with a random secret generated at startup. Before, the app used a fixed default secret that anyone could use to create valid tokens, including administrator tokens.
- Upgraded `anyio` to 4.14.2 or later and `msgpack` to 1.2.3 or later to fix known vulnerabilities.
- Semgrep is no longer installed in the project environment. It pins vulnerable versions of `mcp` and `opentelemetry-api`; install it with `uv tool install semgrep==1.182.1` instead.
- `scripts/lighthouse_audit.py` now only opens `http` and `https` URLs.

## [1.0.0]

### Added

- First release: game and achievement API, game library, upcoming releases, administrator dashboard, file uploads, user directory, sign-up, and English, Portuguese, German, and French translations.
