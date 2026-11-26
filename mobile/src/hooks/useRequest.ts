import { useCallback, useEffect, useState } from 'react';

import { ApiError, NetworkError } from '@/api';

type Result<T> = { key: string; data: T | null; error: string | null; status: number | null };

/**
 * Run `fetcher` whenever `key` changes (pass null to skip). Loading is derived from the
 * key, so no state is set synchronously inside the effect. `refresh()` refetches while
 * keeping the current data on screen (pull-to-refresh); `retry()` refetches from scratch.
 */
export function useRequest<T>(key: string | null, fetcher: (signal: AbortSignal) => Promise<T>) {
  const [attempt, setAttempt] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const [result, setResult] = useState<Result<T> | null>(null);
  const fullKey = key === null ? null : `${key}#${attempt}`;

  useEffect(() => {
    if (fullKey === null) return;
    const controller = new AbortController();
    fetcher(controller.signal)
      .then((data) => setResult({ key: fullKey, data, error: null, status: null }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message =
          error instanceof ApiError || error instanceof NetworkError
            ? error.message
            : String(error);
        setResult((prev) => ({
          key: fullKey,
          // A failed refresh keeps what was already shown.
          data: prev?.key.startsWith(`${key}#`) ? prev.data : null,
          error: message,
          status: error instanceof ApiError ? error.status : null,
        }));
      })
      .finally(() => !controller.signal.aborted && setRefreshing(false));
    return () => controller.abort();
    // `fullKey` identifies the request; the fetcher is recreated every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fullKey]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  const refresh = useCallback(() => {
    setRefreshing(true);
    setAttempt((n) => n + 1);
  }, []);

  const current = result?.key === fullKey ? result : null;
  const stale = refreshing && result?.key.startsWith(`${key}#`) ? result : null;
  return {
    data: current?.data ?? stale?.data ?? null,
    error: current?.error ?? null,
    /** HTTP status of the failure, e.g. 404. */
    errorStatus: current?.status ?? null,
    loading: fullKey !== null && !current && !stale,
    refreshing,
    retry,
    refresh,
  };
}
