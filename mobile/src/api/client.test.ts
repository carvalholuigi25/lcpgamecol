import { createMemoryTokenStore, type TokenStore } from '@/auth/types';

import { createApiClient } from './client';
import { ApiError, NetworkError, SessionExpiredError } from './errors';

import { resolveAssetUrl } from './index';

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(async () => null),
  setItemAsync: jest.fn(async () => {}),
  deleteItemAsync: jest.fn(async () => {}),
}));

type Call = { url: string; init: RequestInit };

function json(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json', ...headers },
  });
}

function setup(
  responder: (call: Call, calls: Call[]) => Response | Promise<Response>,
  tokens: TokenStore = createMemoryTokenStore({
    accessToken: 'access-1',
    refreshToken: 'refresh-1',
  }),
) {
  const calls: Call[] = [];
  const onSessionExpired = jest.fn();
  const fetchMock = jest.fn(async (url: string, init: RequestInit) => {
    const call = { url, init };
    calls.push(call);
    return responder(call, calls);
  });
  const client = createApiClient({
    baseUrl: 'http://api.test',
    tokens,
    fetch: fetchMock as unknown as typeof fetch,
    onSessionExpired,
  });
  return { client, calls, tokens, onSessionExpired };
}

const authHeader = (call: Call | undefined) =>
  (call?.init.headers as Record<string, string> | undefined)?.Authorization;

describe('requests', () => {
  it('sends the access token and parses JSON', async () => {
    const { client, calls } = setup(() => json(200, { username: 'admin' }));

    await expect(client.get('/users')).resolves.toEqual({ username: 'admin' });
    expect(calls[0]?.url).toBe('http://api.test/users');
    expect(authHeader(calls[0])).toBe('Bearer access-1');
    expect(calls[0]?.init.credentials).toBe('omit');
  });

  it('builds query strings and skips empty values', async () => {
    const { client, calls } = setup(() => json(200, []));

    await client.get('/games/page', { query: { page: 2, search: 'zelda', genre: undefined } });

    expect(calls[0]?.url).toBe('http://api.test/games/page?page=2&search=zelda');
  });

  it('sends JSON and form bodies', async () => {
    const { client, calls } = setup(() => json(200, {}));

    await client.post('/feedback', { message: 'hi' });
    await client.request('/auth/token', { form: { username: 'a', password: 'b' }, auth: false });

    expect(calls[0]?.init.body).toBe('{"message":"hi"}');
    expect((calls[0]?.init.headers as Record<string, string>)['Content-Type']).toBe(
      'application/json',
    );
    expect(calls[1]?.init.body).toBe('username=a&password=b');
    expect(authHeader(calls[1])).toBeUndefined();
  });

  it('returns undefined for 204 responses', async () => {
    const { client } = setup(() => new Response(null, { status: 204 }));
    await expect(client.post('/auth/logout')).resolves.toBeUndefined();
  });
});

describe('errors', () => {
  it('raises ApiError with the FastAPI detail', async () => {
    const { client } = setup(() => json(404, { detail: 'Game not found' }));

    const error = await client.get('/games/1').catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 404, detail: 'Game not found', isNotFound: true });
  });

  it('exposes validation issues', async () => {
    const issue = { loc: ['body', 'title'], msg: 'Field required', type: 'missing' };
    const { client } = setup(() => json(422, { detail: [issue] }));

    const error = (await client.post('/games', {}).catch((e: unknown) => e)) as ApiError;

    expect(error.isValidation).toBe(true);
    expect(error.detail).toBe('Field required');
    expect(error.issues).toEqual([issue]);
  });

  it('reads Retry-After on 429', async () => {
    const { client } = setup(() => json(429, { detail: 'Login locked' }, { 'retry-after': '42' }));

    const error = (await client.get('/x').catch((e: unknown) => e)) as ApiError;

    expect(error.isRateLimited).toBe(true);
    expect(error.retryAfter).toBe(42);
  });

  it('wraps fetch failures in NetworkError', async () => {
    const { client } = setup(() => {
      throw new TypeError('Network request failed');
    });

    await expect(client.get('/games')).rejects.toBeInstanceOf(NetworkError);
  });
});

describe('refresh after 401', () => {
  it('refreshes once, stores the rotated pair and retries', async () => {
    const { client, calls, tokens } = setup((call) => {
      if (call.url.endsWith('/auth/refresh')) {
        return json(200, {
          access_token: 'access-2',
          refresh_token: 'refresh-2',
          token_type: 'bearer',
        });
      }
      return authHeader(call) === 'Bearer access-2'
        ? json(200, { ok: true })
        : json(401, { detail: 'Invalid or expired authentication token' });
    });

    await expect(client.get('/users')).resolves.toEqual({ ok: true });

    expect(calls.map((c) => c.url)).toEqual([
      'http://api.test/users',
      'http://api.test/auth/refresh',
      'http://api.test/users',
    ]);
    expect(authHeader(calls[1])).toBe('Bearer refresh-1');
    await expect(tokens.getAccessToken()).resolves.toBe('access-2');
    await expect(tokens.getRefreshToken()).resolves.toBe('refresh-2');
  });

  it('shares one refresh between concurrent requests', async () => {
    const { client, calls } = setup((call) => {
      if (call.url.endsWith('/auth/refresh')) {
        return json(200, { access_token: 'access-2', refresh_token: 'refresh-2' });
      }
      return authHeader(call) === 'Bearer access-2' ? json(200, {}) : json(401, {});
    });

    await Promise.all([client.get('/a'), client.get('/b'), client.get('/c')]);

    expect(calls.filter((c) => c.url.endsWith('/auth/refresh'))).toHaveLength(1);
  });

  it('retries only once', async () => {
    const { client, calls } = setup((call) =>
      call.url.endsWith('/auth/refresh')
        ? json(200, { access_token: 'access-2', refresh_token: 'refresh-2' })
        : json(401, { detail: 'nope' }),
    );

    const error = (await client.get('/users').catch((e: unknown) => e)) as ApiError;

    expect(error.status).toBe(401);
    expect(calls).toHaveLength(3);
  });

  it('ends the session when the refresh is rejected', async () => {
    const { client, tokens, onSessionExpired } = setup((call) =>
      call.url.endsWith('/auth/refresh')
        ? json(401, { detail: 'Invalid refresh token' })
        : json(401, {}),
    );

    await expect(client.get('/users')).rejects.toBeInstanceOf(SessionExpiredError);
    expect(onSessionExpired).toHaveBeenCalledTimes(1);
    await expect(tokens.getRefreshToken()).resolves.toBeNull();
  });

  it('does not refresh for /auth endpoints or anonymous requests', async () => {
    const { client, calls } = setup(() => json(401, { detail: 'Incorrect username or password' }));

    await expect(client.request('/auth/token', { form: {} })).rejects.toBeInstanceOf(ApiError);
    await expect(client.get('/users', { auth: false })).rejects.toBeInstanceOf(ApiError);

    expect(calls).toHaveLength(2);
  });

  it('does not refresh when signed out', async () => {
    const { client, calls } = setup(() => json(401, {}), createMemoryTokenStore());

    await expect(client.get('/users')).rejects.toBeInstanceOf(ApiError);
    expect(calls).toHaveLength(1);
  });

  it('uses cookies instead of headers on the web', async () => {
    const cookieStore: TokenStore = { ...createMemoryTokenStore(), usesCookies: true };
    const { client, calls } = setup((call, all) => {
      if (call.url.endsWith('/auth/refresh')) {
        return json(200, { access_token: 'x', refresh_token: 'y' });
      }
      return all.length === 1 ? json(401, {}) : json(200, { ok: true });
    }, cookieStore);

    await expect(client.get('/users')).resolves.toEqual({ ok: true });

    expect(calls.every((c) => c.init.credentials === 'include')).toBe(true);
    expect(calls.every((c) => authHeader(c) === undefined)).toBe(true);
  });
});

describe('resolveAssetUrl', () => {
  it.each([
    [null, null],
    ['', null],
    ['https://images.igdb.com/a.jpg', 'https://images.igdb.com/a.jpg'],
    ['//images.igdb.com/a.jpg', 'https://images.igdb.com/a.jpg'],
    ['/admin/uploads/abc?inline=true', 'http://cdn.test/admin/uploads/abc?inline=true'],
    ['admin/uploads/abc', 'http://cdn.test/admin/uploads/abc'],
  ])('%p -> %p', (value, expected) => {
    expect(resolveAssetUrl(value, 'http://cdn.test/')).toBe(expected);
  });
});
