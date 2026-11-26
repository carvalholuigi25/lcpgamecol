import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

import { NetworkError, onSessionExpired } from '@/api';

import * as authService from './service';
import type { LoginResult, SessionUser } from './service';

export type SessionState =
  | { status: 'loading'; user: null }
  | { status: 'signedOut'; user: null }
  /** `user` is null when the session was restored offline. */
  | { status: 'signedIn'; user: SessionUser | null };

type SessionContextValue = SessionState & {
  signIn(username: string, password: string): Promise<LoginResult>;
  verifyTwoFactor(challengeToken: string, code: string): Promise<void>;
  resendTwoFactorCode(challengeToken: string): Promise<void>;
  signOut(): Promise<void>;
};

const SessionContext = createContext<SessionContextValue | null>(null);

const signedOut: SessionState = { status: 'signedOut', user: null };

async function loadUser(): Promise<SessionUser | null> {
  try {
    return await authService.fetchSessionUser();
  } catch (error) {
    if (error instanceof NetworkError) return null; // keep the session; we're just offline
    throw error;
  }
}

/** Restores the stored session on launch and exposes sign-in / sign-out to the app. */
export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<SessionState>({ status: 'loading', user: null });

  useEffect(() => {
    let cancelled = false;
    authService
      .hasStoredSession()
      .then((stored) => (stored ? loadUser() : Promise.reject(new Error('no session'))))
      // Only settle the initial "loading" state: a sign-in that finished first wins.
      .then((user) => {
        if (!cancelled)
          setState((s) => (s.status === 'loading' ? { status: 'signedIn', user } : s));
      })
      .catch(() => {
        if (!cancelled) setState((s) => (s.status === 'loading' ? signedOut : s));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // A refresh that fails anywhere in the app ends the session.
  useEffect(() => onSessionExpired(() => setState(signedOut)), []);

  const signIn = useCallback(async (username: string, password: string) => {
    const result = await authService.login(username, password);
    if (result.kind === 'signedIn') setState({ status: 'signedIn', user: await loadUser() });
    return result;
  }, []);

  const verifyTwoFactor = useCallback(async (challengeToken: string, code: string) => {
    await authService.verifyTwoFactor(challengeToken, code);
    setState({ status: 'signedIn', user: await loadUser() });
  }, []);

  const signOut = useCallback(async () => {
    await authService.logout();
    setState(signedOut);
  }, []);

  const value = useMemo<SessionContextValue>(
    () => ({
      ...state,
      signIn,
      verifyTwoFactor,
      resendTwoFactorCode: authService.resendTwoFactorCode,
      signOut,
    }),
    [state, signIn, verifyTwoFactor, signOut],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error('useSession must be used inside <SessionProvider>');
  return value;
}
