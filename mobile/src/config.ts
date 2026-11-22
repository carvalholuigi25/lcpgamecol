// EXPO_PUBLIC_* values are inlined at build time; they must be read with static
// dot notation (process.env.EXPO_PUBLIC_API_URL) to be replaced.
const DEFAULT_API_URL = 'http://localhost:8000';

export function normalizeBaseUrl(url: string | undefined): string {
  const value = (url ?? '').trim() || DEFAULT_API_URL;
  return value.replace(/\/+$/, '');
}

export const API_URL = normalizeBaseUrl(process.env.EXPO_PUBLIC_API_URL);
