import { api, type Schemas } from '@/api';

import { tokenStore } from './tokenStore';

/** GET /users/me/permissions — who the session belongs to. */
export type SessionUser = { username: string; role: string; permissions: string[] };

/** POST /auth/token answers with this instead of tokens when two-factor sign-in is on. */
export type TwoFactorChallenge = {
  two_factor_required: true;
  challenge_token: string;
  /** "totp" (authenticator app) or "email". */
  method: string;
  expires_in: number;
  /** Masked address the code was sent to (email method only). */
  email?: string;
};

type TokenResponse = Schemas['TokenPair'] & { token_type?: string };

export type LoginResult =
  { kind: 'signedIn' } | { kind: 'twoFactor'; challenge: TwoFactorChallenge };

async function storeTokens(pair: TokenResponse) {
  // On the web the server also sets HttpOnly cookies and the web token store ignores this.
  await tokenStore.setTokens({ accessToken: pair.access_token, refreshToken: pair.refresh_token });
}

function isChallenge(body: unknown): body is TwoFactorChallenge {
  return (
    typeof body === 'object' &&
    body !== null &&
    (body as { two_factor_required?: unknown }).two_factor_required === true
  );
}

/** POST /auth/token (OAuth2 password form). Stores the tokens unless 2FA is required. */
export async function login(username: string, password: string): Promise<LoginResult> {
  const body = await api.request<TokenResponse | TwoFactorChallenge>('/auth/token', {
    method: 'POST',
    form: { username: username.trim(), password },
    auth: false,
  });
  if (isChallenge(body)) return { kind: 'twoFactor', challenge: body };
  await storeTokens(body);
  return { kind: 'signedIn' };
}

/** POST /auth/two-factor/verify — finish a 2FA sign-in with an app, email or recovery code. */
export async function verifyTwoFactor(challengeToken: string, code: string): Promise<void> {
  const pair = await api.request<TokenResponse>('/auth/two-factor/verify', {
    method: 'POST',
    json: { challenge_token: challengeToken, code: code.replace(/\s+/g, '') },
    auth: false,
  });
  await storeTokens(pair);
}

/** POST /auth/two-factor/resend — email a new code for the same challenge. */
export async function resendTwoFactorCode(challengeToken: string): Promise<void> {
  await api.request('/auth/two-factor/resend', {
    method: 'POST',
    json: { challenge_token: challengeToken },
    auth: false,
  });
}

/** GET /users/me/permissions with the stored credentials. */
export function fetchSessionUser(): Promise<SessionUser> {
  return api.request<SessionUser>('/users/me/permissions', { method: 'GET' });
}

/** True when this device holds tokens (always "maybe" on the web, where cookies carry them). */
export async function hasStoredSession(): Promise<boolean> {
  if (tokenStore.usesCookies) return true;
  const [access, refresh] = await Promise.all([
    tokenStore.getAccessToken(),
    tokenStore.getRefreshToken(),
  ]);
  return Boolean(access || refresh);
}

/** POST /auth/logout (revokes the refresh token), then forget the tokens locally either way. */
export async function logout(): Promise<void> {
  try {
    const refreshToken = await tokenStore.getRefreshToken();
    await api.request('/auth/logout', {
      method: 'POST',
      ...(refreshToken ? { json: { refresh_token: refreshToken } } : {}),
    });
  } catch {
    // Offline or already expired: the local sign-out below still happens.
  } finally {
    await tokenStore.clear();
  }
}

/** POST /auth/register — create a viewer account (no tokens; sign in afterwards). */
export async function register(username: string, password: string): Promise<void> {
  await api.request('/auth/register', {
    method: 'POST',
    json: { username: username.trim(), password },
    auth: false,
  });
}

/** POST /auth/password-reset/request — emails a reset link if the account has an address. */
export async function requestPasswordReset(identifier: string): Promise<string> {
  const reply = await api.request<{ detail: string }>('/auth/password-reset/request', {
    method: 'POST',
    json: { identifier: identifier.trim() },
    auth: false,
  });
  return reply.detail;
}

/**
 * The reset email holds a link like https://host/reset-password?token=abc. Accept the
 * whole link or just the token.
 */
export function extractResetToken(input: string): string {
  const value = input.trim();
  const match = /[?&]token=([^&#\s]+)/.exec(value);
  return match?.[1] ? decodeURIComponent(match[1]) : value;
}

/** GET /auth/password-reset/check — whether a reset token is still usable, and for whom. */
export function checkResetToken(token: string) {
  return api.request<{ valid: boolean; username: string | null }>('/auth/password-reset/check', {
    method: 'GET',
    query: { token },
    auth: false,
  });
}

/** POST /auth/password-reset/confirm — set the new password (ends all other sessions). */
export async function confirmPasswordReset(token: string, password: string): Promise<string> {
  const reply = await api.request<{ username: string; detail: string }>(
    '/auth/password-reset/confirm',
    { method: 'POST', json: { token, password }, auth: false },
  );
  return reply.username;
}
