import { act, fireEvent, render, screen } from '@testing-library/react-native';

import { api, NetworkError } from '@/api';
import SplashScreen from '@/app/index';
import { ThemeProvider } from '@/theme';

const mockReplace = jest.fn();
jest.mock('expo-router', () => ({ router: { replace: (href: unknown) => mockReplace(href) } }));

let mockSessionStatus: 'loading' | 'signedIn' | 'signedOut' = 'signedIn';
jest.mock('@/auth', () => ({ useSession: () => ({ status: mockSessionStatus }) }));

const getSpy = jest.spyOn(api, 'get');

async function renderSplash() {
  await render(
    <ThemeProvider initialPreference="light">
      <SplashScreen />
    </ThemeProvider>,
  );
}

describe('SplashScreen', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    mockReplace.mockClear();
    mockSessionStatus = 'signedIn';
    getSpy.mockReset();
  });

  afterEach(() => jest.useRealTimers());

  it('redirects to the main screen once config has loaded and the minimum time passed', async () => {
    getSpy.mockResolvedValue({ api_version: '1' });
    await renderSplash();
    expect(mockReplace).not.toHaveBeenCalled();

    await act(async () => {
      await jest.runAllTimersAsync();
    });
    expect(mockReplace).toHaveBeenCalledWith('/home');
  });

  it('shows an error with a retry that tries again', async () => {
    getSpy.mockRejectedValueOnce(new NetworkError('offline'));
    await renderSplash();
    await act(async () => {
      await jest.runAllTimersAsync();
    });
    expect(screen.getByText('Try again')).toBeTruthy();
    expect(mockReplace).not.toHaveBeenCalled();

    getSpy.mockResolvedValueOnce({ api_version: '1' });
    await fireEvent.press(screen.getByText('Try again'));
    await act(async () => {
      await jest.runAllTimersAsync();
    });
    expect(mockReplace).toHaveBeenCalledWith('/home');
  });

  it('sends a signed-out user to the sign-in screen', async () => {
    mockSessionStatus = 'signedOut';
    getSpy.mockResolvedValue({ api_version: '1' });
    await renderSplash();
    await act(async () => {
      await jest.runAllTimersAsync();
    });
    expect(mockReplace).toHaveBeenCalledWith('/login');
  });

  it('waits for the session check before leaving', async () => {
    mockSessionStatus = 'loading';
    getSpy.mockResolvedValue({ api_version: '1' });
    await renderSplash();
    await act(async () => {
      await jest.runAllTimersAsync();
    });
    expect(mockReplace).not.toHaveBeenCalled();
  });
});
