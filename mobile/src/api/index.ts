import { tokenStore } from '@/auth/tokenStore';
import { API_URL } from '@/config';

import { createApiClient } from './client';

export { createApiClient } from './client';
export type { ApiClient, RequestOptions, Schemas } from './client';
export { ApiError, NetworkError, SessionExpiredError } from './errors';

type SessionListener = () => void;
const sessionListeners = new Set<SessionListener>();

/** Subscribe to "the session ended and could not be refreshed" (used by the session provider). */
export function onSessionExpired(listener: SessionListener): () => void {
  sessionListeners.add(listener);
  return () => sessionListeners.delete(listener);
}

export const api = createApiClient({
  baseUrl: API_URL,
  tokens: tokenStore,
  onSessionExpired: () => sessionListeners.forEach((listener) => listener()),
});

let configuredAssetBaseUrl: string = API_URL;

/** Remember the asset base URL from GET /client/config (loaded by the splash screen). */
export function setAssetBaseUrl(url: string | null | undefined): void {
  configuredAssetBaseUrl = url?.trim() || API_URL;
}

/**
 * Covers, avatars and uploads may be stored as paths such as /admin/uploads/<id>.
 * Resolve them against the asset base URL from GET /client/config.
 */
export function resolveAssetUrl(
  value: string | null | undefined,
  assetBaseUrl: string = configuredAssetBaseUrl,
): string | null {
  if (!value) return null;
  if (/^https?:\/\//i.test(value)) return value;
  if (value.startsWith('//')) return `https:${value}`;
  const base = assetBaseUrl.replace(/\/+$/, '');
  return `${base}${value.startsWith('/') ? '' : '/'}${value}`;
}
