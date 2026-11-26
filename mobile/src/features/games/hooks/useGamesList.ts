import { useCallback, useEffect, useRef, useState } from 'react';

import {
  errorMessage,
  fetchGamesPage,
  searchGames,
  type Game,
  type GameSort,
  type SortOrder,
} from '../services';

export const GAMES_PAGE_SIZE = 20;

type Params = { sort?: GameSort | undefined; order?: SortOrder | undefined; search?: string };

type ListState = {
  /** Which params (+ reload) these items belong to; a different key means "loading". */
  key: string;
  items: Game[];
  /** Known total for the plain list; null while searching (the search API has no count). */
  total: number | null;
  /** Whether another page may exist. */
  more: boolean;
  failed: boolean;
  error: string | null;
  refreshing: boolean;
  loadingMore: boolean;
};

const emptyState = (key: string): ListState => ({
  key,
  items: [],
  total: null,
  more: false,
  failed: false,
  error: null,
  refreshing: false,
  loadingMore: false,
});

/** Offset paging can repeat a row when games are added meanwhile; keep the first copy. */
function appendUnique(current: Game[], next: Game[]): Game[] {
  const seen = new Set(current.map((game) => game.id));
  return [...current, ...next.filter((game) => !seen.has(game.id))];
}

async function fetchPage(params: Params, skip: number, signal: AbortSignal) {
  const query = {
    skip,
    limit: GAMES_PAGE_SIZE,
    ...(params.sort ? { sort: params.sort } : {}),
    ...(params.order ? { order: params.order } : {}),
    signal,
  };
  const title = params.search?.trim();
  if (title) {
    const items = await searchGames({ ...query, title });
    return { items, total: null, more: items.length === GAMES_PAGE_SIZE };
  }
  const page = await fetchGamesPage(query);
  return { items: page.items, total: page.total, more: skip + page.items.length < page.total };
}

/**
 * Paged games for an infinite-scroll list. Changing `sort`, `order` or `search` starts
 * over from page one; `loadMore()` appends, `refresh()` (pull-to-refresh) and `retry()`
 * reload.
 */
export function useGamesList({ sort, order, search = '' }: Params = {}) {
  const [reload, setReload] = useState(0);
  const key = JSON.stringify([sort ?? null, order ?? null, search.trim(), reload]);
  const [state, setState] = useState<ListState>(() => emptyState(''));
  const moreController = useRef<AbortController | null>(null);

  // First page whenever the params (or the reload counter) change.
  useEffect(() => {
    const controller = new AbortController();
    moreController.current?.abort();
    fetchPage({ sort, order, search }, 0, controller.signal)
      .then((page) => setState({ ...emptyState(key), ...page }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState((s) => ({
          ...s,
          // A failed pull-to-refresh keeps the games already on screen.
          ...(s.refreshing ? {} : { ...emptyState(key), failed: true }),
          key,
          error: errorMessage(error),
          refreshing: false,
        }));
      });
    return () => controller.abort();
    // `key` already encodes sort/order/search/reload.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  useEffect(() => () => moreController.current?.abort(), []);

  const loading = state.key !== key && !state.refreshing;
  const status: 'loading' | 'ready' | 'error' = loading
    ? 'loading'
    : state.failed
      ? 'error'
      : 'ready';

  const refresh = useCallback(() => {
    setState((s) => ({ ...s, refreshing: true, loadingMore: false, error: null }));
    setReload((n) => n + 1);
  }, []);

  const retry = useCallback(() => setReload((n) => n + 1), []);

  const { items, more, loadingMore, refreshing } = state;

  const loadMore = useCallback(() => {
    if (status !== 'ready' || loadingMore || refreshing || !more) return;
    const controller = new AbortController();
    moreController.current = controller;
    setState((s) => ({ ...s, loadingMore: true, error: null }));
    fetchPage({ sort, order, search }, items.length, controller.signal)
      .then((page) =>
        setState((s) =>
          s.key !== key
            ? s
            : {
                ...s,
                items: appendUnique(s.items, page.items),
                total: page.total,
                more: page.more,
                loadingMore: false,
              },
        ),
      )
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState((s) => ({ ...s, loadingMore: false, error: errorMessage(error) }));
      });
  }, [status, loadingMore, refreshing, more, items.length, sort, order, search, key]);

  return {
    items: loading ? [] : state.items,
    total: state.total,
    status,
    error: state.error,
    refreshing,
    loadingMore,
    hasMore: more,
    refresh,
    retry,
    loadMore,
  };
}
