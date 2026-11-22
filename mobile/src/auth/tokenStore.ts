import * as SecureStore from 'expo-secure-store';

import type { TokenStore } from './types';

// Native (Android/iOS): tokens live in the Keychain / Keystore through expo-secure-store,
// never in AsyncStorage. The access token is also kept in memory to avoid a native call
// per request. The web build uses tokenStore.web.ts instead.
const ACCESS_KEY = 'lcpgamecol.access_token';
const REFRESH_KEY = 'lcpgamecol.refresh_token';

let accessToken: string | null | undefined;

export const tokenStore: TokenStore = {
  usesCookies: false,

  async getAccessToken() {
    if (accessToken === undefined) accessToken = await SecureStore.getItemAsync(ACCESS_KEY);
    return accessToken;
  },

  getRefreshToken() {
    return SecureStore.getItemAsync(REFRESH_KEY);
  },

  async setTokens({ accessToken: access, refreshToken }) {
    accessToken = access;
    await Promise.all([
      SecureStore.setItemAsync(ACCESS_KEY, access),
      SecureStore.setItemAsync(REFRESH_KEY, refreshToken),
    ]);
  },

  async clear() {
    accessToken = null;
    await Promise.all([
      SecureStore.deleteItemAsync(ACCESS_KEY),
      SecureStore.deleteItemAsync(REFRESH_KEY),
    ]);
  },
};
