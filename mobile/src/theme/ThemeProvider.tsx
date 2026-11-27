import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Appearance, useColorScheme } from 'react-native';

import { buildTheme, type ColorScheme, type Theme } from './tokens';

/** "system" follows the device setting, like the web's "auto" theme. */
export type ThemePreference = 'system' | ColorScheme;

type ThemeContextValue = {
  theme: Theme;
  preference: ThemePreference;
  setPreference: (preference: ThemePreference) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function resolveScheme(
  preference: ThemePreference,
  system: string | null | undefined,
): ColorScheme {
  if (preference !== 'system') return preference;
  return system === 'dark' ? 'dark' : 'light';
}

export function ThemeProvider({
  children,
  initialPreference = 'system',
}: {
  children: ReactNode;
  initialPreference?: ThemePreference;
}) {
  const system = useColorScheme();
  const [preference, setPreference] = useState<ThemePreference>(initialPreference);
  // Native UI (tab bar, alerts, keyboards) follows the app-level appearance, not our
  // context, so mirror the preference there. 'auto' removes the override.
  useEffect(() => {
    Appearance.setColorScheme(preference === 'system' ? 'auto' : preference);
  }, [preference]);
  const value = useMemo(
    () => ({ theme: buildTheme(resolveScheme(preference, system)), preference, setPreference }),
    [preference, system],
  );
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useThemeSettings(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) throw new Error('useThemeSettings must be used inside <ThemeProvider>');
  return context;
}

export function useTheme(): Theme {
  return useThemeSettings().theme;
}
