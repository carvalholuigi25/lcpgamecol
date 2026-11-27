// EXPO_PUBLIC_* values are inlined at build time; they must be read with static
// dot notation (process.env.EXPO_PUBLIC_API_URL) to be replaced.
// const DEFAULT_API_URL = 'http://10.0.2.2:8000';

import { Platform } from 'react-native';

const IS_SSL_ENABLED = false;
const MYLOCALIP = () => {
  return Platform.OS === 'android' ? '10.0.2.2' : Platform.OS === 'ios' ? '127.0.0.1' : 'localhost';
};

const PORT = 8000;
const PARTHTTP = IS_SSL_ENABLED ? 's' : '';
const DEFAULT_API_URL = 'http' + PARTHTTP + '://' + MYLOCALIP() + ':' + PORT;

export function normalizeBaseUrl(url: string | undefined): string {
  const value = (url ?? '').trim() || DEFAULT_API_URL;
  return value.replace(/\/+$/, '');
}

export const API_URL = normalizeBaseUrl(DEFAULT_API_URL ?? process.env.EXPO_PUBLIC_API_URL);
