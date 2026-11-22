import { act, render, screen } from '@testing-library/react-native';
import { Text } from 'react-native';

import { ThemeProvider, colors, resolveScheme, useThemeSettings } from './index';

describe('resolveScheme', () => {
  it('follows the system setting', () => {
    expect(resolveScheme('system', 'dark')).toBe('dark');
    expect(resolveScheme('system', 'light')).toBe('light');
    expect(resolveScheme('system', null)).toBe('light');
  });

  it('lets an explicit choice win', () => {
    expect(resolveScheme('light', 'dark')).toBe('light');
    expect(resolveScheme('dark', 'light')).toBe('dark');
  });
});

describe('tokens', () => {
  it('defines the same color roles for light and dark', () => {
    expect(Object.keys(colors.dark).sort()).toEqual(Object.keys(colors.light).sort());
  });
});

describe('ThemeProvider', () => {
  let settings: ReturnType<typeof useThemeSettings> | undefined;

  function Probe() {
    settings = useThemeSettings();
    return <Text>{settings.theme.scheme}</Text>;
  }

  it('switches theme when the preference changes', async () => {
    await render(
      <ThemeProvider initialPreference="light">
        <Probe />
      </ThemeProvider>,
    );
    expect(screen.getByText('light')).toBeTruthy();

    await act(async () => settings?.setPreference('dark'));

    expect(screen.getByText('dark')).toBeTruthy();
    expect(settings?.theme.colors.background).toBe(colors.dark.background);
  });
});
