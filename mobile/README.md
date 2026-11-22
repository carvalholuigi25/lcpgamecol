# lcpgamecol mobile

Expo (SDK 58) + Expo Router client for Android, iOS and the web. See `../PLANS.md` for the roadmap.

## Run

```bash
cp .env.example .env.local   # set EXPO_PUBLIC_API_URL (phones need your LAN address)
npm install
npm start                    # or: npm run web / npm run android / npm run ios
```

Start the backend from the repository root (`npm run startapp`). The Expo web dev server
(`http://localhost:8081`) is in the backend's default `CORS_ORIGINS`.

## Checks

```bash
npm run check     # typecheck + lint + Jest (the CI job in .github/workflows/mobile.yml)
npm run format    # Prettier
```

## Layout

| Path | What |
| --- | --- |
| `src/app/` | Expo Router screens (every file is a route) |
| `src/api/` | `fetch` client: auth header, one retry through `/auth/refresh` after a 401, typed errors |
| `src/api/schema.d.ts` | Generated from `../openapi.json`; do not edit |
| `src/auth/` | Token storage: `expo-secure-store` on native, HttpOnly cookies on the web |
| `src/i18n/` | i18next over the shared `../locales/<lang>.json` (also used by the web pages) |
| `src/theme/` | Color, spacing and type tokens ported from the SCSS; light, dark, follow system |

## API types

After changing a backend route or schema:

```bash
python scripts/export_openapi.py   # from the repository root; writes openapi.json
npm run api:types                  # in mobile/; regenerates src/api/schema.d.ts
```

Commit both files. CI fails when `schema.d.ts` does not match `openapi.json`.

## Translations

Strings live in `../locales/<lang>.json`, keyed by the English text, with `{name}`
placeholders. The web bundle (`scripts/minify_js.mjs`) and this app both read them, and
`metro.config.js` adds that folder to Metro's `watchFolders`.
