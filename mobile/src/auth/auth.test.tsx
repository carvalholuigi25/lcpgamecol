import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';

import { Text } from 'react-native';

import { api, ApiError } from '@/api';
import { LoginForm } from '@/features/auth';
import { ThemeProvider } from '@/theme';

import { SessionProvider, useSession } from './SessionProvider';
import { login, logout, verifyTwoFactor } from './service';
import { tokenStore } from './tokenStore';

jest.mock('./tokenStore', () => {
  const { createMemoryTokenStore } = jest.requireActual('./types');
  return { tokenStore: createMemoryTokenStore() };
});

const requestSpy = jest.spyOn(api, 'request');
const tokens = { access_token: 'access-1', refresh_token: 'refresh-1', token_type: 'bearer' };
const me = { username: 'luigi', role: 'user', permissions: [] };

beforeEach(async () => {
  requestSpy.mockReset();
  await tokenStore.clear();
});

describe('auth service', () => {
  it('posts the OAuth2 form and stores the token pair', async () => {
    requestSpy.mockResolvedValueOnce(tokens);
    await expect(login(' luigi ', 'secret')).resolves.toEqual({ kind: 'signedIn' });
    expect(requestSpy).toHaveBeenCalledWith('/auth/token', {
      method: 'POST',
      form: { username: 'luigi', password: 'secret' },
      auth: false,
    });
    await expect(tokenStore.getAccessToken()).resolves.toBe('access-1');
    await expect(tokenStore.getRefreshToken()).resolves.toBe('refresh-1');
  });

  it('returns the 2FA challenge without storing anything, then verifies the code', async () => {
    const challenge = {
      two_factor_required: true,
      challenge_token: 'ch',
      method: 'email',
      expires_in: 300,
    };
    requestSpy.mockResolvedValueOnce(challenge);
    await expect(login('luigi', 'secret')).resolves.toEqual({ kind: 'twoFactor', challenge });
    await expect(tokenStore.getAccessToken()).resolves.toBeNull();

    requestSpy.mockResolvedValueOnce(tokens);
    await verifyTwoFactor('ch', '123 456');
    expect(requestSpy).toHaveBeenLastCalledWith(
      '/auth/two-factor/verify',
      expect.objectContaining({ json: { challenge_token: 'ch', code: '123456' }, auth: false }),
    );
    await expect(tokenStore.getAccessToken()).resolves.toBe('access-1');
  });

  it('logout revokes the refresh token and clears tokens even when the call fails', async () => {
    await tokenStore.setTokens({ accessToken: 'a', refreshToken: 'r' });
    requestSpy.mockRejectedValueOnce(new ApiError(500, {}));
    await logout();
    expect(requestSpy).toHaveBeenCalledWith(
      '/auth/logout',
      expect.objectContaining({ json: { refresh_token: 'r' } }),
    );
    await expect(tokenStore.getRefreshToken()).resolves.toBeNull();
  });
});

function Status() {
  const { status, user } = useSession();
  return <Text>{`${status}:${user?.username ?? '-'}`}</Text>;
}

async function renderLogin() {
  await render(
    <ThemeProvider initialPreference="light">
      <SessionProvider>
        <Status />
        <LoginForm onTwoFactor={jest.fn()} />
      </SessionProvider>
    </ThemeProvider>,
  );
}

describe('SessionProvider + LoginForm', () => {
  it('starts signed out without stored tokens', async () => {
    await renderLogin();
    await waitFor(() => expect(screen.getByText('signedOut:-')).toBeTruthy());
    expect(requestSpy).not.toHaveBeenCalled();
  });

  it('validates empty fields before calling the API', async () => {
    await renderLogin();
    await fireEvent.press(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByText('Enter your username.')).toBeTruthy();
    expect(screen.getByText('Enter your password.')).toBeTruthy();
    expect(requestSpy).not.toHaveBeenCalled();
  });

  it('signs in and loads the user', async () => {
    await renderLogin();
    requestSpy.mockResolvedValueOnce(tokens).mockResolvedValueOnce(me);
    await fireEvent.changeText(screen.getByTestId('login-username'), 'luigi');
    await fireEvent.changeText(screen.getByTestId('login-password'), 'secret');
    await fireEvent.press(screen.getByRole('button', { name: 'Sign in' }));
    await waitFor(() => expect(screen.getByText('signedIn:luigi')).toBeTruthy());
  });

  it('shows a friendly message for wrong credentials', async () => {
    await renderLogin();
    requestSpy.mockRejectedValueOnce(
      new ApiError(401, { detail: 'Incorrect username or password' }),
    );
    await fireEvent.changeText(screen.getByTestId('login-username'), 'luigi');
    await fireEvent.changeText(screen.getByTestId('login-password'), 'nope');
    await fireEvent.press(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByTestId('login-error')).toHaveTextContent(
      'Incorrect username or password.',
    );
    expect(screen.getByText('signedOut:-')).toBeTruthy();
  });
});
