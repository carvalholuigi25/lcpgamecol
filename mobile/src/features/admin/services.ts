import { api } from '@/api';

import type { AdminUser } from '../users/services';

// Admin-only endpoints (require_admin on the backend). Like the users module, the backend
// returns untyped dicts here, so their shapes are written out from the route code.

const opts = (signal?: AbortSignal) => (signal ? { signal } : {});
const path = (value: string) => encodeURIComponent(value);

// --- dashboard (routes/admin/__init__.py) -------------------------------------------------

export type CountBucket = { label: string; count: number };

export type Dashboard = {
  overview: {
    games: number;
    achievements: number;
    unlocked_achievements: number;
    achievement_completion: number;
    wishlist: number;
    hours_played: number;
    average_user_rating: number;
    average_critic_rating: number;
  };
  release_years: CountBucket[];
  genres: CountBucket[];
  platforms: CountBucket[];
  achievement_types: CountBucket[];
  recent_games: { id: number; title: string; release_year: number }[];
};

export const fetchDashboard = (signal?: AbortSignal) =>
  api.get<Dashboard>('/admin/dashboard', opts(signal));

/** Bar widths (0–100) relative to the largest bucket. */
export function barShares(buckets: CountBucket[]): number[] {
  const max = Math.max(0, ...buckets.map((b) => b.count));
  return buckets.map((b) => (max > 0 ? Math.round((b.count / max) * 100) : 0));
}

// --- moderation (routes/games/moderation.py) ----------------------------------------------

export type PostKind = 'review' | 'comment';
export type PostStatus = 'visible' | 'pending' | 'hidden';
export type ModerationAction = 'approve' | 'hide' | 'remove' | 'lock' | 'unlock';

export type ContentReport = {
  reporter: string;
  reason: string;
  details: string | null;
  created_at: string;
};

export type ModerationItem = {
  kind: PostKind;
  id: number;
  game_id: number;
  game_title: string;
  username: string;
  display_name: string | null;
  body: string | null;
  status: PostStatus;
  locked: boolean | number;
  created_at: string;
  rating: number | null;
  open_reports: number;
  reports: ContentReport[];
};

export type ModerationQueue = {
  items: ModerationItem[];
  counts: { pending: number; hidden: number; reported: number };
};

export const fetchModerationQueue = (signal?: AbortSignal) =>
  api.get<ModerationQueue>('/admin/moderation/queue', opts(signal));

/** Approve, hide, remove, lock or unlock a post. `note` is sent to the author. */
export function moderatePost(
  item: Pick<ModerationItem, 'kind' | 'id'>,
  action: ModerationAction,
  note?: string,
) {
  const trimmed = note?.trim();
  return api.post(
    `/admin/moderation/${item.kind}/${item.id}/${action}`,
    trimmed ? { note: trimmed } : {},
  );
}

/** Reviews and comments store HTML; show them as plain text in the queue. */
export function plainText(html: string | null | undefined): string {
  return (html ?? '')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/(p|div|li)>/gi, '\n')
    .replace(/<[^>]*>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, '&')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

// --- feedback (routes/users/feedback.py) --------------------------------------------------

export const FEEDBACK_STATUSES = ['open', 'in_progress', 'answered', 'closed'] as const;
export type FeedbackStatus = (typeof FEEDBACK_STATUSES)[number];

export const FEEDBACK_STATUS_LABELS: Record<FeedbackStatus, string> = {
  open: 'Open',
  in_progress: 'In progress',
  answered: 'Answered',
  closed: 'Closed',
};

export type Feedback = {
  id: number;
  username: string;
  category: 'bug' | 'idea' | 'question' | 'praise' | 'other';
  subject: string;
  message: string;
  page_url: string | null;
  status: FeedbackStatus;
  reply: string | null;
  replied_by: string | null;
  replied_at: string | null;
  created_at: string;
  updated_at: string;
  email_status: string | null;
};

export type FeedbackInbox = {
  items: Feedback[];
  counts: Record<FeedbackStatus, number>;
  email_enabled: boolean;
};

export const fetchFeedback = (status: FeedbackStatus | null, signal?: AbortSignal) =>
  api.get<FeedbackInbox>('/admin/feedback', {
    query: { status: status ?? undefined },
    ...opts(signal),
  });

/** Change the status and/or reply (a new reply on an open item marks it answered). */
export const updateFeedback = (id: number, body: { status?: FeedbackStatus; reply?: string }) =>
  api.put<Feedback>(`/admin/feedback/${id}`, body);

export const deleteFeedback = (id: number) => api.delete(`/admin/feedback/${id}`);

// --- accounts (routes/admin/users.py, routes/admin/permissions.py) ------------------------

export type Permission = { key: string; label: string; description: string };

export type PermissionsOverview = {
  permissions: Permission[];
  users: { username: string; role: string; source: string; permissions: string[] }[];
};

export const fetchPermissions = (signal?: AbortSignal) =>
  api.get<PermissionsOverview>('/admin/permissions/api', opts(signal));

export const updatePermissions = (username: string, permissions: string[]) =>
  api.put<{ username: string; permissions: string[] }>(`/admin/permissions/api/${path(username)}`, {
    permissions,
  });

export const fetchAccount = (username: string, signal?: AbortSignal) =>
  api.get<AdminUser>(`/admin/users/${path(username)}`, opts(signal));

export const updateRole = (username: string, role: 'admin' | 'viewer') =>
  api.put<AdminUser>(`/admin/users/${path(username)}/role`, { role });

export type PasswordResetLink = { link: string; expires_in: number; emailed: boolean };

export const createPasswordResetLink = (username: string) =>
  api.post<PasswordResetLink>(`/admin/users/${path(username)}/password-reset`);

export const turnOffTwoFactor = (username: string) =>
  api.delete(`/admin/users/${path(username)}/two-factor`);

/** Everything the manage-account screen needs in one request pair. */
export async function loadAccount(username: string, signal?: AbortSignal) {
  const [account, overview] = await Promise.all([
    fetchAccount(username, signal),
    fetchPermissions(signal),
  ]);
  const grants =
    overview.users.find((u) => u.username.toLowerCase() === account.username.toLowerCase())
      ?.permissions ?? [];
  return { account, permissions: overview.permissions, grants };
}

/** Configured (AUTH_USERS) accounts are managed in the server settings, not the app. */
export const isConfigured = (account: Pick<AdminUser, 'source'>) => account.source === 'configured';

export const toggle = (list: string[], key: string) =>
  list.includes(key) ? list.filter((k) => k !== key) : [...list, key];
