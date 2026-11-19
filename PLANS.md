# Plans

## Cross-platform client in React Native

### Goal

Build one React Native code base that runs on Android, iOS, and the web, and talks to the existing FastAPI backend. The current server-rendered pages (`pages/`, `public/scripts/`) keep working while the new client grows. When the new client covers everything they do, decide whether to retire them.

### Decisions

| Topic | Choice | Why |
| --- | --- | --- |
| Framework | **Expo** (managed workflow, latest SDK) with TypeScript | One project for Android, iOS, and web (through `react-native-web`). EAS builds iOS apps without a Mac. |
| Navigation | **Expo Router** (file-based) | The same routes become URLs on the web (`/library`, `/library/releases`, `/profile`) and deep links on mobile. |
| Server data | **TanStack Query** | Caching, retries, pagination, and refetch when the app comes back to the foreground. Live events only need to invalidate queries. |
| Local state | React context, or Zustand if it grows | Little global state: session, preferences, theme. |
| API types | Generated from `/openapi.json` with `openapi-typescript` | Request and response types stay in step with the Pydantic schemas. |
| Styling | `StyleSheet` plus a small theme module (tokens for color, spacing, type) | Ports the existing light, dark, and seasonal themes without a heavy UI kit. |
| Forms | `react-hook-form` + `zod` | Login, registration, reviews, profile, feedback. |
| Live updates | `@microsoft/signalr` | The backend already speaks SignalR at `/hubs/library` and accepts `access_token` in the query string. |
| Translations | `i18next` + `react-i18next` + `expo-localization` | Reuse the strings in `public/scripts/i18n.js` (en, it, es, ja). |
| Secure storage | `expo-secure-store` on mobile; HttpOnly cookie on the web | Tokens never go into `AsyncStorage` or `localStorage`. |
| Tests | Jest + React Native Testing Library; Playwright for the web build; Maestro for mobile flows later | Matches the "browser tests" item in `TODO.md`. |

### Repository layout

Keep the client in this repository so API changes and client changes land together:

```text
lcpgamecol/
├── backend/, routes/, main.py ...   # existing FastAPI app
└── mobile/                          # new Expo app
    ├── app/                         # Expo Router screens
    │   ├── (auth)/login.tsx, register.tsx, reset-password.tsx, two-factor.tsx
    │   ├── (tabs)/library/index.tsx, library/[gameId].tsx, releases.tsx,
    │   │         inbox.tsx, profile.tsx
    │   ├── feedback.tsx
    │   └── admin/ ...               # later phase
    ├── src/
    │   ├── api/                     # fetch client, generated types, endpoint hooks
    │   ├── auth/                    # session provider, token storage per platform
    │   ├── realtime/                # SignalR connection and query invalidation
    │   ├── i18n/                    # locales/*.json
    │   ├── theme/
    │   └── components/
    ├── app.config.ts
    └── package.json
```

`mobile/` gets its own `package.json`. The root `package.json` stays for the Sass build and server scripts; add helper scripts such as `"mobile": "npm --prefix mobile run start"`.

### Backend changes needed first

The API already returns JSON and Bearer tokens, so most endpoints work as they are. These gaps block or weaken a native client:

1. **Configurable API origin and CORS.** Add the Expo web dev server (`http://localhost:8081`) and the production web origin to `CORS_ORIGINS`. Native apps send no `Origin`, so the CSRF check in `_is_trusted_origin` already lets them through; keep it that way only for Bearer requests, never for cookie requests.
2. **Refresh token rotation and revocation.** `/auth/refresh` returns a new access token but keeps the same refresh token for 7 days, and `/auth/logout` only deletes the cookie. Mobile clients keep refresh tokens for a long time, so:
   - return a new refresh token on every refresh and reject reused ones;
   - store refresh token IDs (`jti`) so `/auth/logout` can revoke the current one;
   - keep `revoke_sessions` working for "sign out everywhere".
3. **Web refresh cookie.** For the web build, put the refresh token in an HttpOnly, `SameSite=Strict` cookie scoped to `/auth/refresh`, so the browser never holds tokens in JavaScript.
4. **OAuth for native apps.** The callback redirects to `/admin` and sets a cookie, which a native app can't use. Add a `redirect` parameter limited to an allowlist (for example `lcpgamecol://auth/callback`) and return a short-lived, one-time code that the app exchanges for tokens at a new `POST /auth/oauth/exchange` endpoint (use PKCE). Open the flow with `expo-auth-session` / `expo-web-browser`.
5. **Live connection checks.** Close SignalR connections when the session expires and apply the access rules to `/hubs/library` (both already in `TODO.md`). Native apps reconnect often, so these matter more now.
6. **Image URLs.** Return absolute URLs (or a base URL) for covers and uploads, so the app can load them from any origin.
7. **Server-side library filters.** The library filters only the 12 games on the current page (`TODO.md`). A mobile list with infinite scroll needs genre, platform, category, and age rating filters on `/games/page`.
8. **Push notifications (later).** Add a `device_tokens` table and an endpoint to register Expo push tokens, then send notifications for messages, moderation results, and release countdowns.

Add tests in `tests/` for each change before the client relies on it.

### Phases

#### Phase 0 — Groundwork (backend)

- [ ] Backend changes 1–3 and 6 above, with tests.
- [ ] Add a script that exports `openapi.json` so the client can generate types without a running server.
- [ ] Extract the dictionaries from `public/scripts/i18n.js` into `locales/<lang>.json`, and have the existing web pages load the same files, so both clients share one source of strings.

#### Phase 1 — Project setup

- [ ] `npx create-expo-app mobile --template` (TypeScript, Expo Router).
- [ ] ESLint, Prettier, strict `tsconfig`, path aliases.
- [ ] API client: base URL from `app.config.ts` (`EXPO_PUBLIC_API_URL`), auth header, one retry after a `401` through `/auth/refresh`, typed errors.
- [ ] Theme tokens ported from the SCSS (light, dark, follow system); seasonal themes later.
- [ ] i18n wired to the shared locale files, with the device language as the default.
- [ ] CI job: type check, lint, and Jest on every push to `dev`.

#### Phase 2 — Sign-in

- [ ] Login, registration, and password reset screens.
- [ ] Two-factor challenge screen (`/auth/two-factor/verify`, `/auth/two-factor/resend`).
- [ ] Session provider: tokens in `expo-secure-store` on mobile and cookies on the web; restore the session on start; sign out.
- [ ] Route guards for signed-out users and for admin-only screens (`/users/me/permissions`).
- [ ] OAuth sign-in after backend change 4.

#### Phase 3 — Library (first usable release)

- [ ] Library list with infinite scroll, search, and filters (`/games/page`, `/games/search`).
- [ ] Game details: cover, artwork, trailers, store and map links, achievements.
- [ ] Wishlist and favorites (`/games/{id}/wishlist`, `/games/{id}/favorite`, `/users/me/game-lists`).
- [ ] Upcoming releases with countdowns (`/games/all-releases`, `/games/next-releases`).
- [ ] Offline reading: persist the TanStack Query cache so the last-seen library opens without a network.

#### Phase 4 — Community features

- [ ] Reviews and comments with reactions and reporting. The web uses Quill for rich text; on mobile, start with a plain-text editor that saves the same safe HTML subset that `backend/moderation/rich_text.py` accepts, and render it with `react-native-render-html`.
- [ ] Inbox: messages and notifications, with unread badges.
- [ ] Profile, XP, rank badges, and leaderboard.
- [ ] Feedback form and "my feedback".
- [ ] Live updates: connect to `/hubs/library`, turn each event into a query invalidation, and reconnect when the app returns to the foreground.

#### Phase 5 — Admin

- [ ] Dashboard, user management, roles, permissions.
- [ ] Moderation queue.
- [ ] IGDB search and import.
- [ ] Uploads (`expo-image-picker` / `expo-document-picker`) and game data import/export.
- [ ] Access control settings. Some admin screens may stay web-only if they are awkward on a phone; decide per screen.

#### Phase 6 — Release

- [ ] App icons, splash screen, and store listings.
- [ ] EAS Build profiles: `development`, `preview` (internal testers), `production`.
- [ ] EAS Update for JavaScript-only fixes between store releases.
- [ ] Web build (`npx expo export --platform web`) served by FastAPI under a path such as `/app`, or by a static host.
- [ ] Crash and error reporting (Sentry for React Native) tied to the backend's error tracking.
- [ ] Push notifications after backend change 8.
- [ ] Privacy policy and data-deletion request (required by both app stores).

### Security checklist

- Tokens only in `expo-secure-store` (mobile) or HttpOnly cookies (web). Never log them.
- HTTPS everywhere outside local development. Android blocks clear-text HTTP by default; keep it that way for release builds.
- Check deep links and OAuth redirects against an allowlist.
- Render user content (reviews, comments, messages) only through the sanitized HTML path; never inject raw HTML on the web build.
- Keep the IGDB credentials on the server. The app only calls this API.
- Run `npm audit` for `mobile/` in the existing security audit script.

### Risks and open questions

- **Rich text editing on mobile** has no drop-in Quill equivalent. Plain text with basic formatting may be enough at first.
- **Single-worker live updates**: more clients mean more SignalR connections in one process. Plan the Redis backplane from `TODO.md` before a public release.
- **Two web front ends**: once the Expo web build matches the server-rendered pages, choose one to keep, so features are not built twice.
- **App store accounts**: an Apple Developer account (paid, yearly) and a Google Play account are needed before Phase 6.
- **Where the API runs**: phones can't reach `127.0.0.1`. Development needs the LAN address (or a tunnel such as `expo start --tunnel`) and a trusted certificate for HTTPS.

### Definition of done for the first release

- Users can sign in (password and two-factor), browse and search the library, see game details and upcoming releases, manage their wishlist and favorites, and get live updates.
- Works on Android, iOS, and a desktop browser, in all four languages, in light and dark themes.
- Backend changes have tests; the client has unit tests for the API layer and auth, and Playwright tests for the web sign-in and library flows.
