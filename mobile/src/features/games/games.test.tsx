import { act, renderHook, waitFor } from '@testing-library/react-native';

import { api, ApiError } from '@/api';

import { useGame } from './hooks/useGame';
import { GAMES_PAGE_SIZE, useGamesList } from './hooks/useGamesList';
import { formatRating, toNameList, type Game } from './services';

const getSpy = jest.spyOn(api, 'get');

const game = (id: number): Game => ({ id, title: `Game ${id}`, genre: 'RPG' }) as Game;
const page = (ids: number[], total: number) => ({
  items: ids.map(game),
  total,
  page_size: GAMES_PAGE_SIZE,
});
const range = (from: number, count: number) => Array.from({ length: count }, (_, i) => from + i);

beforeEach(() => getSpy.mockReset());

describe('toNameList', () => {
  it('normalizes strings, string arrays and {name} objects', () => {
    expect(toNameList(null)).toEqual([]);
    expect(toNameList('PC, PlayStation 5')).toEqual(['PC', 'PlayStation 5']);
    expect(toNameList(['PC', 'Xbox'])).toEqual(['PC', 'Xbox']);
    expect(
      toNameList([
        { id: 1, name: 'Co-op' },
        { id: 2, name: null },
      ]),
    ).toEqual(['Co-op']);
  });
});

describe('formatRating', () => {
  it('hides unrated and rounds to one decimal', () => {
    expect(formatRating(0)).toBeNull();
    expect(formatRating(null)).toBeNull();
    expect(formatRating(8.46)).toBe('8.5');
    expect(formatRating(9)).toBe('9');
  });
});

describe('useGamesList', () => {
  it('loads the first page, then the next one on loadMore', async () => {
    getSpy
      .mockResolvedValueOnce(page(range(1, GAMES_PAGE_SIZE), 25))
      .mockResolvedValueOnce(page(range(GAMES_PAGE_SIZE + 1, 5), 25));

    const { result } = await renderHook(() => useGamesList());
    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(getSpy.mock.calls[0]?.[1]).not.toHaveProperty('auth', false);
    expect(result.current.items).toHaveLength(GAMES_PAGE_SIZE);
    expect(result.current.hasMore).toBe(true);
    expect(getSpy).toHaveBeenLastCalledWith(
      '/games/page',
      expect.objectContaining({ query: { skip: 0, limit: GAMES_PAGE_SIZE } }),
    );

    await act(async () => result.current.loadMore());
    await waitFor(() => expect(result.current.items).toHaveLength(25));
    expect(result.current.hasMore).toBe(false);
    expect(getSpy).toHaveBeenLastCalledWith(
      '/games/page',
      expect.objectContaining({ query: { skip: GAMES_PAGE_SIZE, limit: GAMES_PAGE_SIZE } }),
    );
  });

  it('reports an error and recovers on retry', async () => {
    getSpy.mockRejectedValueOnce(new ApiError(500, { detail: 'boom' }));
    const { result } = await renderHook(() => useGamesList());
    await waitFor(() => expect(result.current.status).toBe('error'));

    getSpy.mockResolvedValueOnce(page([1], 1));
    await act(async () => result.current.retry());
    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(result.current.items).toHaveLength(1);
  });
});

describe('useGamesList search and sort', () => {
  it('uses /games/search while searching and pages until a short page', async () => {
    getSpy
      .mockResolvedValueOnce(range(1, GAMES_PAGE_SIZE).map(game))
      .mockResolvedValueOnce([game(99)]);
    const { result } = await renderHook(() => useGamesList({ search: 'zel' }));
    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(getSpy).toHaveBeenLastCalledWith(
      '/games/search',
      expect.objectContaining({ query: { title: 'zel', skip: 0, limit: GAMES_PAGE_SIZE } }),
    );
    expect(result.current.total).toBeNull();
    expect(result.current.hasMore).toBe(true);

    await act(async () => result.current.loadMore());
    await waitFor(() => expect(result.current.items).toHaveLength(GAMES_PAGE_SIZE + 1));
    expect(result.current.hasMore).toBe(false);
  });

  it('starts over when the sort changes', async () => {
    getSpy.mockResolvedValueOnce(page([1, 2], 2)).mockResolvedValueOnce(page([2, 1], 2));
    const { result, rerender } = await renderHook(
      (props: { sort: 'added' | 'title' }) => useGamesList(props),
      { initialProps: { sort: 'added' } },
    );
    await waitFor(() => expect(result.current.items.map((g) => g.id)).toEqual([1, 2]));

    await rerender({ sort: 'title' });
    await waitFor(() => expect(result.current.items.map((g) => g.id)).toEqual([2, 1]));
    expect(getSpy).toHaveBeenLastCalledWith(
      '/games/page',
      expect.objectContaining({ query: { skip: 0, limit: GAMES_PAGE_SIZE, sort: 'title' } }),
    );
  });
});

describe('useGame', () => {
  it('loads a game by id', async () => {
    getSpy.mockResolvedValueOnce(game(7));
    const { result } = await renderHook(() => useGame('7'));
    await waitFor(() => expect(result.current.game?.title).toBe('Game 7'));
    expect(getSpy).toHaveBeenCalledWith('/games/7', expect.anything());
    // Games routes require the session, so the request must not opt out of auth.
    expect(getSpy.mock.calls[0]?.[1]).not.toHaveProperty('auth', false);
  });

  it('flags a 404 as not found', async () => {
    getSpy.mockRejectedValueOnce(new ApiError(404, { detail: 'Game not found' }));
    const { result } = await renderHook(() => useGame('999'));
    await waitFor(() => expect(result.current.notFound).toBe(true));
  });

  it('treats an invalid id as not found without calling the API', async () => {
    const { result } = await renderHook(() => useGame('abc'));
    expect(result.current.notFound).toBe(true);
    expect(getSpy).not.toHaveBeenCalled();
  });
});
