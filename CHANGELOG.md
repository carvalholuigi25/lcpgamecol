# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

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

- `GET /users` now returns the signed-in user's `role` as well as their `username`.
- The **Liquid glass** theme was redesigned for the library and the administrator pages: translucent panels over a slowly moving colour background, light edges on panels, glass-style buttons and inputs, and a see-through details dialog. It falls back to solid panels when the browser can't blur the background or the system asks for reduced transparency, and it stops animating when reduced motion is requested.
- Automatic and live dashboard refreshes no longer discard unsaved changes in the game or achievement forms, and they keep the selected game.

### Fixed

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
