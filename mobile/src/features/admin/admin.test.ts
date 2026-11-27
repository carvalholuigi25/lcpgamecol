import { api } from '@/api';

import {
  barShares,
  createPasswordResetLink,
  fetchFeedback,
  loadAccount,
  moderatePost,
  plainText,
  toggle,
  turnOffTwoFactor,
  updateFeedback,
  updatePermissions,
  updateRole,
} from './services';

const getSpy = jest.spyOn(api, 'get');
const postSpy = jest.spyOn(api, 'post');
const putSpy = jest.spyOn(api, 'put');
const deleteSpy = jest.spyOn(api, 'delete');

beforeEach(() => {
  for (const spy of [getSpy, postSpy, putSpy, deleteSpy]) {
    spy.mockReset();
    spy.mockResolvedValue(undefined);
  }
});

describe('barShares', () => {
  it('scales counts to the largest bucket', () => {
    expect(
      barShares([
        { label: 'RPG', count: 8 },
        { label: 'Racing', count: 2 },
      ]),
    ).toEqual([100, 25]);
  });

  it('handles empty and all-zero data', () => {
    expect(barShares([])).toEqual([]);
    expect(barShares([{ label: 'x', count: 0 }])).toEqual([0]);
  });
});

describe('plainText', () => {
  it('strips tags and decodes entities from stored HTML', () => {
    expect(plainText('<p>Great &amp; <b>fun</b></p><p>10/10</p>')).toBe('Great & fun\n10/10');
    expect(plainText(null)).toBe('');
  });
});

describe('moderatePost', () => {
  it('posts to the kind/id/action endpoint with an optional trimmed note', async () => {
    await moderatePost({ kind: 'review', id: 7 }, 'hide', '  spoilers ');
    expect(postSpy).toHaveBeenCalledWith('/admin/moderation/review/7/hide', { note: 'spoilers' });
    await moderatePost({ kind: 'comment', id: 3 }, 'approve');
    expect(postSpy).toHaveBeenLastCalledWith('/admin/moderation/comment/3/approve', {});
  });
});

describe('feedback', () => {
  it('filters by status, or lists everything', async () => {
    await fetchFeedback('open');
    expect(getSpy).toHaveBeenCalledWith('/admin/feedback', { query: { status: 'open' } });
    await fetchFeedback(null);
    expect(getSpy).toHaveBeenLastCalledWith('/admin/feedback', { query: { status: undefined } });
  });

  it('replies through PUT /admin/feedback/{id}', async () => {
    await updateFeedback(4, { reply: 'Thanks!' });
    expect(putSpy).toHaveBeenCalledWith('/admin/feedback/4', { reply: 'Thanks!' });
  });
});

describe('account management', () => {
  it('encodes usernames in every account endpoint', async () => {
    await updateRole('a b', 'admin');
    await updatePermissions('a b', ['games.edit']);
    await createPasswordResetLink('a b');
    await turnOffTwoFactor('a b');
    expect(putSpy).toHaveBeenCalledWith('/admin/users/a%20b/role', { role: 'admin' });
    expect(putSpy).toHaveBeenCalledWith('/admin/permissions/api/a%20b', {
      permissions: ['games.edit'],
    });
    expect(postSpy).toHaveBeenCalledWith('/admin/users/a%20b/password-reset');
    expect(deleteSpy).toHaveBeenCalledWith('/admin/users/a%20b/two-factor');
  });

  it('loadAccount picks the grants of that user, ignoring case', async () => {
    getSpy.mockImplementation(async (path: string) =>
      path.startsWith('/admin/users/')
        ? { username: 'Ana', role: 'viewer', source: 'registered' }
        : {
            permissions: [{ key: 'games.edit', label: 'Edit games', description: '' }],
            users: [
              { username: 'bob', permissions: ['games.delete'] },
              { username: 'ana', permissions: ['games.edit'] },
            ],
          },
    );
    const result = await loadAccount('Ana');
    expect(result.grants).toEqual(['games.edit']);
    expect(result.permissions).toHaveLength(1);
  });

  it('toggle adds or removes a key', () => {
    expect(toggle(['a'], 'b')).toEqual(['a', 'b']);
    expect(toggle(['a', 'b'], 'a')).toEqual(['b']);
  });
});
