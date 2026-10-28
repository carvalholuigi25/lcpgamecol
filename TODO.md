# TODO

Planned work and known gaps. Move items to `CHANGELOG.md` when they ship.

## Live updates

- [ ] Share live events between server processes (for example, with Redis) so the app can run more than one worker. Today each process only reaches its own connections.
- [ ] Close live connections when the sign-in session expires. Today a connection stays open until the browser disconnects.
- [ ] Refresh the user directory and special features pages when profiles, favorites, or uploads change.
- [ ] Add a `profilesChanged` event for administrators when a user changes their favorites.

## Features

- [ ] Implement feedback page.
- [ ] Implement notifications and messages icon with their dialogs.
- [ ] Implement review system with moderation filters & commands.
- [ ] Add a basic xp level + rank system (or gamification).
- [ ] Add cool personalization for user profile.

## Wishlist and favorites

- [ ] Add "My wishlist" and "My favorites" filters to the library.
- [ ] Let users upload their own avatar and cover images. Today only administrators can upload, so viewers must paste an image link.
- [ ] Count per-user wishlists on the dashboard. The **Wishlist** card still uses the shared `wishlisted` field, and that field could then be removed.
- [ ] Decide whether viewers should be able to add releases to the shared library. Today, wishlisting or favoriting a release imports it for everyone.
- [ ] Refresh imported games from IGDB (titles, dates, and covers change before release).

## Library

- [ ] Let administrators edit a game inside the details dialog, without opening the dashboard.
- [ ] Offer an "Undo" right after a game is deleted.

## Quality

- [ ] Find and fix the `Unexpected token 'export'` error logged when the library loads (one of the scripts loaded from `/nmodules` is an ES module but is loaded as a classic script).
- [ ] Add placeholder images for seed achievements whose icons return 404.
- [ ] Add browser tests for the library and dashboard (Playwright).
- [ ] Add a check that fails when a UI string has no translation.
