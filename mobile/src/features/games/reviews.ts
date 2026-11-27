import { api } from '@/api';

// routes/games/reviews.py — one review (1-5 stars, optional text) per user and game.

export type ReviewStatus = 'visible' | 'pending' | 'hidden';

export type Review = {
  id: number;
  game_id: number;
  username: string;
  display_name: string | null;
  rating: number;
  /** Rich text (HTML from the web editor) or plain text from older posts. */
  body: string | null;
  created_at: string;
  updated_at: string;
  status: ReviewStatus;
  locked: boolean;
  reported: boolean;
  reactions: { emoji: string; count: number }[];
  my_reaction: string | null;
};

export type ReviewList = {
  /** Visible reviews only; `average` is null when there are none. */
  count: number;
  average: number | null;
  rating_max: number;
  /** The signed-in user's own review, whatever its status. */
  mine: Review | null;
  items: Review[];
};

export const REVIEW_BODY_MAX_LENGTH = 2000;

/** GET /games/{id}/reviews — 409 while the game is unreleased. */
export function fetchReviews(gameId: number, signal?: AbortSignal) {
  return api.get<ReviewList>(`/games/${gameId}/reviews`, {
    query: { limit: 50 },
    ...(signal ? { signal } : {}),
  });
}

/** PUT /games/{id}/reviews/mine — create or replace the signed-in user's review. */
export function saveMyReview(gameId: number, rating: number, text: string) {
  const body = textToHtml(text);
  return api.put<Review>(`/games/${gameId}/reviews/mine`, { rating, body: body || null });
}

/** DELETE /games/{id}/reviews/{reviewId} — authors delete their own, admins anyone's. */
export function deleteReview(gameId: number, reviewId: number) {
  return api.delete<void>(`/games/${gameId}/reviews/${reviewId}`);
}

export type ReactionSummary = Pick<Review, 'reactions' | 'my_reaction'>;

/** The reactions the web offers on every post (public/scripts/games/reviews.js). */
export const STANDARD_REACTIONS = [
  { emoji: '👍', label: 'Like' },
  { emoji: '👎', label: 'Dislike' },
  { emoji: '❤️', label: 'Love' },
  { emoji: '😡', label: 'Hate' },
] as const;

/**
 * POST /games/{id}/reviews/{reviewId}/reactions — one reaction per user: the same emoji
 * removes it, another replaces it. 409 when the review is locked or not visible.
 */
export function toggleReviewReaction(gameId: number, reviewId: number, emoji: string) {
  return api.post<ReactionSummary>(`/games/${gameId}/reviews/${reviewId}/reactions`, { emoji });
}

export type ReportReason = 'spam' | 'offensive' | 'spoilers' | 'off_topic' | 'other';

export const REPORT_REASONS: { reason: ReportReason; label: string }[] = [
  { reason: 'spam', label: 'Spam' },
  { reason: 'offensive', label: 'Offensive' },
  { reason: 'spoilers', label: 'Spoilers' },
  { reason: 'off_topic', label: 'Off topic' },
  { reason: 'other', label: 'Other' },
];

export const REPORT_DETAILS_MAX_LENGTH = 300;

/**
 * POST /games/{id}/reviews/{reviewId}/report — 400 for your own review, 409 when already
 * reported. `hidden` is true when this report pushed the review past the hide threshold.
 */
export function reportReview(
  gameId: number,
  reviewId: number,
  reason: ReportReason,
  details: string,
) {
  return api.post<{ reported: boolean; hidden: boolean }>(
    `/games/${gameId}/reviews/${reviewId}/report`,
    { reason, details: details.trim() || null },
  );
}

const ENTITIES: Record<string, string> = {
  amp: '&',
  lt: '<',
  gt: '>',
  quot: '"',
  apos: "'",
  nbsp: ' ',
};

/** Review HTML (or plain text) as plain text with line breaks, for display and editing. */
export function htmlToText(value: string | null | undefined): string {
  if (!value) return '';
  if (!/<[a-z][\s\S]*>/i.test(value)) return value.trim();
  return value
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<li[^>]*>/gi, '• ')
    .replace(/<\/(p|li|blockquote)>/gi, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&(#x?[0-9a-f]+|\w+);/gi, (entity, code: string) => {
      if (code.startsWith('#')) {
        const n =
          code[1]?.toLowerCase() === 'x' ? parseInt(code.slice(2), 16) : Number(code.slice(1));
        return Number.isFinite(n) ? String.fromCodePoint(n) : entity;
      }
      return ENTITIES[code.toLowerCase()] ?? entity;
    })
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

/**
 * Plain text from the mobile editor as the paragraphs the web editor produces, escaped so
 * text like "<3" is never read as markup by the server's rich-text cleaner.
 */
export function textToHtml(text: string): string {
  const escape = (line: string) =>
    line.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const lines = text.trim().split(/\r?\n/);
  if (lines.length === 1 && !lines[0]) return '';
  return lines.map((line) => (line.trim() ? `<p>${escape(line)}</p>` : '<p><br></p>')).join('');
}
