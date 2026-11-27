import { api, ApiError } from '@/api';

import {
  filterUsers,
  initials,
  loadUserProfile,
  type AdminUser,
  type LeaderboardEntry,
} from './services';

const getSpy = jest.spyOn(api, 'get');
beforeEach(() => getSpy.mockReset());

const admin = { username: 'boss', role: 'admin', permissions: [] };
const viewer = { username: 'luigi', role: 'viewer', permissions: [] };

const xp = {
  xp: 120,
  level: 3,
  max_level: 30,
  rank: 'Explorer',
  rank_key: 'explorer',
  next_rank: { name: 'Adventurer', level: 5 },
  level_xp: 100,
  next_level_xp: 200,
  progress: 20,
};

const adminUser: AdminUser = {
  username: 'ana',
  role: 'viewer',
  source: 'registered',
  created_at: '2026-01-02 10:00:00',
  display_name: 'Ana Silva',
  bio: 'RPG fan',
  location: 'Lisbon',
  avatar_url: '/admin/uploads/a.png',
  cover_url: null,
  email: 'ana@example.com',
  two_factor_enabled: true,
  xp: 120,
  rank: { level: 3, rank: 'Explorer', rank_key: 'explorer' },
  updated_at: null,
  favorite_games: [],
  hours_in_favorites: 12.5,
};

describe('initials', () => {
  it('uses first and last word, or the first two letters', () => {
    expect(initials('Ana Maria Silva')).toBe('AS');
    expect(initials('luigi')).toBe('LU');
  });
});

describe('loadUserProfile', () => {
  it('admins read the full profile from /admin/users/{username}', async () => {
    getSpy.mockResolvedValueOnce(adminUser);
    const profile = await loadUserProfile('ana', admin);
    expect(getSpy).toHaveBeenCalledWith('/admin/users/ana', {});
    expect(profile).toMatchObject({
      displayName: 'Ana Silva',
      email: 'ana@example.com',
      twoFactorEnabled: true,
      level: { level: 3, rank: 'Explorer', xp: 120 },
      limited: false,
    });
    expect(profile.avatarUrl).toMatch(/\/admin\/uploads\/a\.png$/);
  });

  it('your own page combines /users/me/profile and /users/me/xp', async () => {
    getSpy.mockImplementation(async (path: string) =>
      path === '/users/me/xp'
        ? xp
        : { ...adminUser, username: 'luigi', wishlist_games: [{ id: 1, title: 'Zelda' }] },
    );
    const profile = await loadUserProfile('Luigi', viewer);
    expect(profile.level).toEqual({
      xp: 120,
      level: 3,
      rank: 'Explorer',
      progress: 20,
      nextRank: 'Adventurer',
    });
    expect(profile.wishlist).toHaveLength(1);
    expect(profile.role).toBe('viewer');
  });

  it('other users fall back to the public leaderboard entry', async () => {
    const entry: LeaderboardEntry = {
      ...xp,
      position: 2,
      username: 'mario',
      display_name: null,
      avatar_url: null,
    };
    getSpy.mockResolvedValueOnce([entry]);
    const profile = await loadUserProfile('mario', viewer);
    expect(getSpy).toHaveBeenCalledWith(
      '/users/xp/leaderboard',
      expect.objectContaining({ query: { limit: 50 } }),
    );
    expect(profile).toMatchObject({ displayName: 'mario', limited: true, email: null });
  });

  it('reports 404 when someone is not on the leaderboard', async () => {
    getSpy.mockResolvedValue([]);
    await expect(loadUserProfile('ghost', viewer)).rejects.toMatchObject({ status: 404 });
    await expect(loadUserProfile('ghost', viewer)).rejects.toBeInstanceOf(ApiError);
  });
});

describe('filterUsers', () => {
  const users = [
    { username: 'ana', display_name: 'Ana Silva', email: 'ana@example.com' },
    { username: 'luigi', display_name: null, email: null },
  ];

  it('matches username, display name or email, ignoring case and blanks', () => {
    expect(filterUsers(users, '  ')).toBe(users);
    expect(filterUsers(users, 'SILVA')).toEqual([users[0]]);
    expect(filterUsers(users, 'example')).toEqual([users[0]]);
    expect(filterUsers(users, 'lui')).toEqual([users[1]]);
    expect(filterUsers(users, 'zzz')).toEqual([]);
  });
});
