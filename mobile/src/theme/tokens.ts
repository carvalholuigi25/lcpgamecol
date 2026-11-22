// Ported from the web theme variables in public/styles/scss/admin.scss
// (body[data-theme="white"] and body[data-theme="dark"]). Seasonal palettes from
// _seasonal_themes.scss come later.

export type ColorScheme = 'light' | 'dark';

export type ThemeColors = {
  /** Page background (--paper). */
  background: string;
  /** Cards and panels (--surface). */
  surface: string;
  /** Main text (--ink). */
  text: string;
  /** Secondary text (--muted). */
  muted: string;
  /** Borders and dividers (--line). */
  border: string;
  /** Primary actions and links (--green). */
  primary: string;
  /** Tinted backgrounds behind primary content (--green-soft). */
  primarySoft: string;
  /** Text on top of `primary`. */
  onPrimary: string;
  /** Destructive actions and errors (--orange). */
  danger: string;
  /** Highlights and warnings (--yellow). */
  warning: string;
};

export const colors: Record<ColorScheme, ThemeColors> = {
  light: {
    background: '#f4f5ef',
    surface: '#fffefa',
    text: '#202823',
    muted: '#747e75',
    border: '#dfe4da',
    primary: '#245f48',
    primarySoft: '#e1ece4',
    onPrimary: '#fffefa',
    danger: '#d76c46',
    warning: '#eab95d',
  },
  dark: {
    background: '#151d1c',
    surface: '#202a28',
    text: '#edf4f0',
    muted: '#a6b4ad',
    border: '#3a4944',
    primary: '#78b89a',
    primarySoft: '#293c34',
    onPrimary: '#151d1c',
    danger: '#f09a75',
    warning: '#e5c46e',
  },
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
} as const;

export const radius = {
  sm: 6,
  md: 10,
  lg: 16,
  pill: 999,
} as const;

// The web uses DM Sans / Fraunces / DM Mono; system fonts until those are bundled.
export const typography = {
  display: { fontSize: 28, lineHeight: 34, fontWeight: '700' },
  title: { fontSize: 20, lineHeight: 26, fontWeight: '600' },
  body: { fontSize: 16, lineHeight: 22, fontWeight: '400' },
  label: { fontSize: 14, lineHeight: 18, fontWeight: '500' },
  caption: { fontSize: 12, lineHeight: 16, fontWeight: '400' },
} as const;

export type Theme = {
  scheme: ColorScheme;
  colors: ThemeColors;
  spacing: typeof spacing;
  radius: typeof radius;
  typography: typeof typography;
};

export function buildTheme(scheme: ColorScheme): Theme {
  return { scheme, colors: colors[scheme], spacing, radius, typography };
}
