import { api } from '@/api';

// routes/games/lists.py — each user's own wishlist and favorite games.

export type GameLists = {
  wishlist: number[];
  favorites: number[];
  /** How many favorites a user may pick (the server answers 409 past it). */
  favorites_max: number;
};

export type GameListState = { game_id: number; wishlisted: boolean; favorite: boolean };

/** GET /users/me/game-lists — the ids on the signed-in user's wishlist and favorites. */
export function fetchMyGameLists(signal?: AbortSignal) {
  return api.get<GameLists>('/users/me/game-lists', signal ? { signal } : {});
}

/** PUT or DELETE /games/{id}/wishlist; answers with the game's new list state. */
export function setWishlisted(gameId: number, on: boolean) {
  const path = `/games/${gameId}/wishlist`;
  return on ? api.put<GameListState>(path) : api.delete<GameListState>(path);
}

/** PUT or DELETE /games/{id}/favorite; PUT answers 409 when the favorites are full. */
export function setFavorite(gameId: number, on: boolean) {
  const path = `/games/${gameId}/favorite`;
  return on ? api.put<GameListState>(path) : api.delete<GameListState>(path);
}
