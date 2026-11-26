import { api, ApiError, resolveAssetUrl } from '@/api';
import type { SessionUser } from '@/auth';

// The backend returns these as untyped dicts (see routes/admin/users.py, routes/users/xp.py
// and backend/gamification/xp.py), so their shapes are written out here.

export const ROLE_ADMIN = 'admin';

/** game_summary() in routes/admin/users.py. */
export type GameSummary = {
  id: number;
  title: string;
  genre: string;
  release_year: number;
  cover_image_url: string | null;
  user_rating: number;
  hours_played: number;
};

/** xp.summary() — level progress. */
export type XpSummary = {
  xp: number;
  level: number;
  max_level: number;
  rank: string;
  rank_key: string;
  next_rank: { name: string; level: number } | null;
  level_xp: number;
  next_level_xp: number | null;
  /** 0–100 towards the next level. */
  progress: number;
};

/** One profile from GET /admin/users (admins only). */
export type AdminUser = {
  username: string;
  role: string;
  source: 'configured' | 'registered';
  created_at: string | null;
  display_name: string | null;
  bio: string | null;
  location: string | null;
  avatar_url: string | null;
  cover_url: string | null;
  email: string | null;
  two_factor_enabled: boolean;
  xp: number;
  rank: { level: number; rank: string; rank_key: string };
  updated_at: string | null;
  favorite_games: GameSummary[];
  hours_in_favorites: number;
};

/** One row of GET /users/xp/leaderboard (any signed-in user). */
export type LeaderboardEntry = XpSummary & {
  position: number;
  username: string;
  display_name: string | null;
  avatar_url: string | null;
};

/** GET /users/me/profile — the caller's own profile plus their wishlist. */
type MyProfile = Omit<AdminUser, 'rank'> & { wishlist_games: GameSummary[] };

/** Everything the user details screen can show, whatever the source. */
export type UserProfile = {
  username: string;
  displayName: string;
  role: string | null;
  bio: string | null;
  location: string | null;
  email: string | null;
  avatarUrl: string | null;
  coverUrl: string | null;
  twoFactorEnabled: boolean | null;
  createdAt: string | null;
  level: {
    xp: number;
    level: number;
    rank: string;
    progress: number | null;
    nextRank: string | null;
  };
  favorites: GameSummary[];
  wishlist: GameSummary[] | null;
  hoursInFavorites: number | null;
  /** True when only public leaderboard data is available (non-admin viewing someone else). */
  limited: boolean;
};

export const LEADERBOARD_MAX = 50;

const path = (username: string) => encodeURIComponent(username);

export const fetchAdminUsers = (signal?: AbortSignal) =>
  api.get<AdminUser[]>('/admin/users', signal ? { signal } : {});

export const fetchLeaderboard = (signal?: AbortSignal) =>
  api.get<LeaderboardEntry[]>('/users/xp/leaderboard', {
    query: { limit: LEADERBOARD_MAX },
    ...(signal ? { signal } : {}),
  });

export const isAdmin = (user: SessionUser | null) => user?.role === ROLE_ADMIN;

export const sameUser = (a: string | null | undefined, b: string | null | undefined) =>
  !!a && !!b && a.toLowerCase() === b.toLowerCase();

/** "Ana Silva" → "AS", "luigi" → "LU". */
export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  const letters =
    words.length > 1 ? `${words[0]![0]}${words[words.length - 1]![0]}` : name.slice(0, 2);
  return letters.toUpperCase();
}

function fromAdmin(user: AdminUser): UserProfile {
  return {
    username: user.username,
    displayName: user.display_name || user.username,
    role: user.role,
    bio: user.bio,
    location: user.location,
    email: user.email,
    avatarUrl: resolveAssetUrl(user.avatar_url),
    coverUrl: resolveAssetUrl(user.cover_url),
    twoFactorEnabled: user.two_factor_enabled,
    createdAt: user.created_at,
    level: {
      xp: user.xp,
      level: user.rank.level,
      rank: user.rank.rank,
      progress: null,
      nextRank: null,
    },
    favorites: user.favorite_games,
    wishlist: null,
    hoursInFavorites: user.hours_in_favorites,
    limited: false,
  };
}

function fromSummary(xp: XpSummary) {
  return {
    xp: xp.xp,
    level: xp.level,
    rank: xp.rank,
    progress: xp.progress,
    nextRank: xp.next_rank?.name ?? null,
  };
}

/**
 * Load the profile for /user/[username], using the richest source the viewer may read:
 * admins → GET /admin/users/{username}; yourself → /users/me/profile + /users/me/xp;
 * anyone else → your entry on the public XP leaderboard.
 */
export async function loadUserProfile(
  username: string,
  viewer: SessionUser | null,
  signal?: AbortSignal,
): Promise<UserProfile> {
  const options = signal ? { signal } : {};

  if (isAdmin(viewer)) {
    return fromAdmin(await api.get<AdminUser>(`/admin/users/${path(username)}`, options));
  }

  if (sameUser(username, viewer?.username)) {
    const [profile, xp] = await Promise.all([
      api.get<MyProfile>('/users/me/profile', options),
      api.get<XpSummary>('/users/me/xp', options),
    ]);
    return {
      ...fromAdmin({ ...profile, role: viewer!.role, rank: { level: 0, rank: '', rank_key: '' } }),
      level: fromSummary(xp),
      wishlist: profile.wishlist_games ?? [],
    };
  }

  const entry = (await fetchLeaderboard(signal)).find((row) => sameUser(row.username, username));
  if (!entry) throw new ApiError(404, { detail: 'User not found' });
  return {
    username: entry.username,
    displayName: entry.display_name || entry.username,
    role: null,
    bio: null,
    location: null,
    email: null,
    avatarUrl: resolveAssetUrl(entry.avatar_url),
    coverUrl: null,
    twoFactorEnabled: null,
    createdAt: null,
    level: fromSummary(entry),
    favorites: [],
    wishlist: null,
    hoursInFavorites: null,
    limited: true,
  };
}
