import type { TokenStore } from '@/auth/types';

import { ApiError, NetworkError, SessionExpiredError } from './errors';
import type { components } from './schema';

export type Schemas = components['schemas'];

type Query = Record<string, string | number | boolean | null | undefined>;

export type RequestOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  /** Sent as JSON. */
  json?: unknown;
  /** Sent as application/x-www-form-urlencoded (the OAuth2 /auth/token form). */
  form?: Record<string, string>;
  query?: Query;
  headers?: Record<string, string>;
  /** Attach credentials and retry once through /auth/refresh after a 401 (default true). */
  auth?: boolean;
  signal?: AbortSignal;
};

export type ApiClientOptions = {
  baseUrl: string;
  tokens: TokenStore;
  fetch?: typeof fetch;
  /** Called once when a refresh fails, so the app can return to the sign-in screen. */
  onSessionExpired?: () => void;
};

export type ApiClient = ReturnType<typeof createApiClient>;

const REFRESH_PATH = '/auth/refresh';

export function createApiClient({
  baseUrl,
  tokens,
  fetch: fetchImpl = (...args) => fetch(...args),
  onSessionExpired,
}: ApiClientOptions) {
  // Refresh tokens work once (the server rotates them and treats reuse as theft), so
  // concurrent 401s must share a single refresh call.
  let refreshing: Promise<void> | null = null;

  function url(path: string, query?: Query): string {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(query ?? {})) {
      if (value !== undefined && value !== null) search.append(key, String(value));
    }
    const suffix = search.toString();
    return `${baseUrl}${path}${suffix ? `?${suffix}` : ''}`;
  }

  async function send(path: string, options: RequestOptions, bearer: string | null) {
    const headers: Record<string, string> = { Accept: 'application/json', ...options.headers };
    let body: string | undefined;
    if (options.json !== undefined) {
      headers['Content-Type'] = 'application/json';
      body = JSON.stringify(options.json);
    } else if (options.form) {
      headers['Content-Type'] = 'application/x-www-form-urlencoded';
      body = new URLSearchParams(options.form).toString();
    }
    // On the web the HttpOnly cookies carry auth; tokens never go into headers there.
    if (bearer && !tokens.usesCookies) headers.Authorization = `Bearer ${bearer}`;

    const init: RequestInit = {
      method: options.method ?? (body === undefined ? 'GET' : 'POST'),
      headers,
      credentials: tokens.usesCookies ? 'include' : 'omit',
    };
    if (body !== undefined) init.body = body;
    if (options.signal) init.signal = options.signal;

    try {
      return await fetchImpl(url(path, options.query), init);
    } catch (error) {
      if (isAbort(error)) throw error;
      throw new NetworkError(error);
    }
  }

  async function refreshOnce(): Promise<void> {
    refreshing ??= (async () => {
      try {
        const refreshToken = await tokens.getRefreshToken();
        if (!tokens.usesCookies && !refreshToken) throw new SessionExpiredError();
        const response = await send(REFRESH_PATH, { method: 'POST' }, refreshToken);
        if (!response.ok) throw new SessionExpiredError();
        const pair = (await response.json()) as Schemas['TokenPair'];
        await tokens.setTokens({
          accessToken: pair.access_token,
          refreshToken: pair.refresh_token,
        });
      } catch (error) {
        if (error instanceof SessionExpiredError) {
          await tokens.clear();
          onSessionExpired?.();
        }
        throw error;
      }
    })().finally(() => {
      refreshing = null;
    });
    return refreshing;
  }

  async function request<T = unknown>(path: string, options: RequestOptions = {}): Promise<T> {
    const useAuth = options.auth ?? true;
    const bearer = useAuth ? await tokens.getAccessToken() : null;
    let response = await send(path, options, bearer);

    const canRetry =
      useAuth &&
      response.status === 401 &&
      !path.startsWith('/auth/') &&
      (tokens.usesCookies || bearer !== null || (await tokens.getRefreshToken()) !== null);
    if (canRetry) {
      await refreshOnce();
      response = await send(path, options, await tokens.getAccessToken());
    }
    return parse<T>(response);
  }

  return {
    baseUrl,
    request,
    get: <T = unknown>(path: string, options?: Omit<RequestOptions, 'method' | 'json'>) =>
      request<T>(path, { ...options, method: 'GET' }),
    post: <T = unknown>(path: string, json?: unknown, options?: Omit<RequestOptions, 'method'>) =>
      request<T>(path, { ...options, method: 'POST', json }),
    put: <T = unknown>(path: string, json?: unknown, options?: Omit<RequestOptions, 'method'>) =>
      request<T>(path, { ...options, method: 'PUT', json }),
    patch: <T = unknown>(path: string, json?: unknown, options?: Omit<RequestOptions, 'method'>) =>
      request<T>(path, { ...options, method: 'PATCH', json }),
    delete: <T = unknown>(path: string, options?: Omit<RequestOptions, 'method'>) =>
      request<T>(path, { ...options, method: 'DELETE' }),
    /** Force a token refresh (e.g. when the app returns to the foreground). */
    refresh: refreshOnce,
  };
}

async function parse<T>(response: Response): Promise<T> {
  const text = response.status === 204 ? '' : await response.text();
  let body: unknown = text;
  if (text && (response.headers.get('content-type') ?? '').includes('json')) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!response.ok) {
    const retryAfter = Number(response.headers.get('retry-after'));
    throw new ApiError(
      response.status,
      body,
      Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : null,
    );
  }
  return (text ? body : undefined) as T;
}

function isAbort(error: unknown): boolean {
  return error instanceof Error && error.name === 'AbortError';
}
