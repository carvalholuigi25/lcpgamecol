import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { I18nextProvider } from 'react-i18next';
import { Text } from 'react-native';

import { api, ApiError } from '@/api';
import { extractResetToken, SessionProvider, useSession } from '@/auth';
import { tokenStore } from '@/auth/tokenStore';
import { i18n } from '@/i18n';
import { ThemeProvider } from '@/theme';

import { ForgotPasswordForm } from './ForgotPasswordForm';
import { RegisterForm } from './RegisterForm';

jest.mock('@/auth/tokenStore', () => {
  const { createMemoryTokenStore } = jest.requireActual('@/auth/types');
  return { tokenStore: createMemoryTokenStore() };
});

const requestSpy = jest.spyOn(api, 'request');
beforeEach(async () => {
  requestSpy.mockReset();
  await tokenStore.clear(); // a successful sign-in in one test must not leak into the next
});

function Status() {
  const { status } = useSession();
  return <Text>{status}</Text>;
}

async function renderWithSession(ui: React.ReactElement) {
  await render(
    <I18nextProvider i18n={i18n}>
      <ThemeProvider initialPreference="light">
        <SessionProvider>
          <Status />
          {ui}
        </SessionProvider>
      </ThemeProvider>
    </I18nextProvider>,
  );
  await waitFor(() => expect(screen.getByText('signedOut')).toBeTruthy());
}

describe('extractResetToken', () => {
  it('accepts the whole email link or just the token', () => {
    expect(extractResetToken(' https://host/reset-password?token=abc%2D1&x=y ')).toBe('abc-1');
    expect(extractResetToken('abc123')).toBe('abc123');
  });
});

describe('RegisterForm', () => {
  const fill = async (username: string, password: string, confirm = password) => {
    await fireEvent.changeText(screen.getByTestId('register-username'), username);
    await fireEvent.changeText(screen.getByTestId('register-password'), password);
    await fireEvent.changeText(screen.getByTestId('register-confirm'), confirm);
    await fireEvent.press(screen.getByRole('button', { name: 'Create account' }));
  };

  it('checks the username rule and matching passwords before calling the API', async () => {
    await renderWithSession(<RegisterForm onNeedsSignIn={jest.fn()} />);
    await fill('-x', 'long enough pass 1', 'different');
    expect(screen.getByText(/Use 3 to 32 letters/)).toBeTruthy();
    expect(screen.getByText('The passwords do not match.')).toBeTruthy();
    expect(requestSpy).not.toHaveBeenCalled();
  });

  it('registers, then signs in with the new account', async () => {
    await renderWithSession(<RegisterForm onNeedsSignIn={jest.fn()} />);
    requestSpy
      .mockResolvedValueOnce({ username: 'newbie', role: 'viewer' }) // register
      .mockResolvedValueOnce({ access_token: 'a', refresh_token: 'r', token_type: 'bearer' })
      .mockResolvedValueOnce({ username: 'newbie', role: 'viewer', permissions: [] });
    await fill('newbie', 'correct horse 42');

    await waitFor(() => expect(screen.getByText('signedIn')).toBeTruthy());
    expect(requestSpy).toHaveBeenNthCalledWith(1, '/auth/register', {
      method: 'POST',
      json: { username: 'newbie', password: 'correct horse 42' },
      auth: false,
    });
    expect(requestSpy).toHaveBeenNthCalledWith(2, '/auth/token', expect.anything());
  });

  it("shows the server's password policy message", async () => {
    await renderWithSession(<RegisterForm onNeedsSignIn={jest.fn()} />);
    requestSpy.mockRejectedValueOnce(new ApiError(400, { detail: 'Use at least 12 characters.' }));
    await fill('newbie', 'short1');
    expect(await screen.findByTestId('register-error')).toHaveTextContent(
      'Use at least 12 characters.',
    );
    expect(screen.getByText('signedOut')).toBeTruthy();
  });
});

describe('ForgotPasswordForm', () => {
  it('requests a link, checks the pasted link and sets the new password', async () => {
    const onBack = jest.fn();
    await renderWithSession(<ForgotPasswordForm onBackToSignIn={onBack} />);

    requestSpy.mockResolvedValueOnce({ detail: 'A reset link is on its way.' });
    await fireEvent.changeText(screen.getByTestId('reset-identifier'), 'luigi@example.com');
    await fireEvent.press(screen.getByRole('button', { name: 'Send reset link' }));
    expect(await screen.findByText('A reset link is on its way.')).toBeTruthy();

    requestSpy.mockResolvedValueOnce({ valid: true, username: 'luigi' });
    await fireEvent.changeText(
      screen.getByTestId('reset-link'),
      'https://host/reset-password?token=tok123',
    );
    await fireEvent.press(screen.getByRole('button', { name: 'Continue' }));
    expect(await screen.findByText('Choose a new password for luigi.')).toBeTruthy();
    expect(requestSpy).toHaveBeenLastCalledWith('/auth/password-reset/check', {
      method: 'GET',
      query: { token: 'tok123' },
      auth: false,
    });

    requestSpy.mockResolvedValueOnce({ username: 'luigi', detail: 'changed' });
    await fireEvent.changeText(screen.getByTestId('reset-password'), 'brand new pass 9');
    await fireEvent.changeText(screen.getByTestId('reset-confirm'), 'brand new pass 9');
    await fireEvent.press(screen.getByRole('button', { name: 'Change password' }));
    expect(await screen.findByText(/Your password was changed, luigi/)).toBeTruthy();
    expect(requestSpy).toHaveBeenLastCalledWith('/auth/password-reset/confirm', {
      method: 'POST',
      json: { token: 'tok123', password: 'brand new pass 9' },
      auth: false,
    });

    await fireEvent.press(screen.getByRole('button', { name: 'Back to sign in' }));
    expect(onBack).toHaveBeenCalled();
  });

  it('rejects an expired link', async () => {
    await renderWithSession(<ForgotPasswordForm onBackToSignIn={jest.fn()} />);
    await fireEvent.press(screen.getByRole('button', { name: 'I already have a link' }));
    requestSpy.mockResolvedValueOnce({ valid: false, username: null });
    await fireEvent.changeText(screen.getByTestId('reset-link'), 'old-token');
    await fireEvent.press(screen.getByRole('button', { name: 'Continue' }));
    expect(await screen.findByTestId('reset-error')).toHaveTextContent(
      'This reset link is invalid or has expired.',
    );
  });
});
