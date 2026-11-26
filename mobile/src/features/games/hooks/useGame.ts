import { useCallback, useEffect, useState } from 'react';

import { ApiError } from '@/api';

import { errorMessage, fetchGame, type Game } from '../services';

type Result = { key: string; game: Game | null; error: string | null; notFound: boolean };

/** Loads one game by the route's `gameId` param. `retry()` fetches it again. */
export function useGame(gameIdParam: string | undefined) {
  const gameId = Number(gameIdParam);
  const validId = Number.isInteger(gameId) && gameId > 0;
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Result | null>(null);

  // Loading is derived: the last result belongs to a different id/attempt.
  const key = `${gameId}:${attempt}`;

  useEffect(() => {
    if (!validId) return;
    const controller = new AbortController();
    fetchGame(gameId, controller.signal)
      .then((game) => setResult({ key, game, error: null, notFound: false }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const notFound = error instanceof ApiError && error.isNotFound;
        setResult({ key, game: null, error: errorMessage(error), notFound });
      });
    return () => controller.abort();
  }, [gameId, validId, key]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  if (!validId) {
    return { game: null, loading: false, error: null, notFound: true, retry };
  }
  const current = result?.key === key ? result : null;
  return {
    game: current?.game ?? null,
    loading: current === null,
    error: current?.error ?? null,
    notFound: current?.notFound ?? false,
    retry,
  };
}
