import type { TokenStore } from './types';

// Web: the backend keeps both tokens in HttpOnly cookies (the refresh cookie is
// SameSite=Strict and scoped to /auth), so JavaScript never holds them and nothing goes
// into localStorage. Requests are sent with credentials instead of an Authorization header.
export const tokenStore: TokenStore = {
  usesCookies: true,
  getAccessToken: async () => null,
  getRefreshToken: async () => null,
  setTokens: async () => {},
  clear: async () => {},
};
