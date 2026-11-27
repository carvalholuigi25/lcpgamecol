import { api, ApiError, NetworkError, resolveAssetUrl, type Schemas } from '@/api';

export type Game = Schemas['Game'];
export type GamePage = Schemas['GamePage'];
export type GameSort = Schemas['GameSort'];
export type SortOrder = Schemas['SortOrder'];

/** Sort options offered in the games screen, in display order. */
export const GAME_SORTS: { sort: GameSort; order?: SortOrder; label: string }[] = [
  { sort: 'added', label: 'Recently added' },
  { sort: 'title', order: 'asc', label: 'Title' },
  { sort: 'release_date', order: 'desc', label: 'Release date' },
  { sort: 'user_rating', order: 'desc', label: 'Rating' },
  { sort: 'hours_played', order: 'desc', label: 'Most played' },
];

export type GamesPageQuery = {
  skip: number;
  limit: number;
  sort?: GameSort;
  order?: SortOrder;
  signal?: AbortSignal;
};

// The backend mounts every route module behind get_current_user (routes/__init__.py), so
// games requests must carry the session: default `auth` (Bearer/cookie + refresh on 401).

/** GET /games/page — one page of games plus the total count (requires sign-in). */
export function fetchGamesPage({ skip, limit, sort, order, signal }: GamesPageQuery) {
  return api.get<GamePage>('/games/page', {
    query: { skip, limit, sort, order },
    ...(signal ? { signal } : {}),
  });
}

/**
 * GET /games/search?title= — case-insensitive title match. Returns a plain list (no total),
 * so callers treat a short page as the last one.
 */
export function searchGames({
  title,
  skip,
  limit,
  sort,
  order,
  signal,
}: GamesPageQuery & { title: string }) {
  return api.get<Game[]>('/games/search', {
    query: { title, skip, limit, sort, order },
    ...(signal ? { signal } : {}),
  });
}

/** GET /games/{id} — a single game (requires sign-in). Throws ApiError 404 when missing. */
export function fetchGame(gameId: number, signal?: AbortSignal) {
  return api.get<Game>(`/games/${gameId}`, signal ? { signal } : {});
}

/** Best image for a list thumbnail / detail hero, resolved against the asset base URL. */
export function gameCoverUrl(game: Game): string | null {
  return resolveAssetUrl(game.cover_image_url || game.image_url || game.screenshot_url);
}

/**
 * Platforms, game modes and editions arrive as an array of strings, an array of
 * `{ id, name }` objects, a comma-separated string or null. Normalize to a string list.
 */
export function toNameList(value: Game['platforms'] | Game['gamemodes'] | Game['editions']) {
  if (!value) return [];
  if (typeof value === 'string') {
    return value
      .split(',')
      .map((part) => part.trim())
      .filter(Boolean);
  }
  return value.map((item) => (typeof item === 'string' ? item : (item.name ?? ''))).filter(Boolean);
}

/** Ratings are shown as-is like the web shelf (one decimal); 0/null means "not rated". */
export function formatRating(value: number | null | undefined): string | null {
  return value ? `${Number(value.toFixed(1))}` : null;
}

/** A user-facing message for a failed request. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError || error instanceof NetworkError) return error.message;
  return error instanceof Error ? error.message : String(error);
}
