import type { ExpoConfig } from 'expo/config';

// The API address comes from EXPO_PUBLIC_API_URL (see .env.example). The app reads it
// through process.env in src/config.ts; it is repeated in `extra` so tools that inspect
// the config (and Constants.expoConfig) can see which backend a build points at.
const config: ExpoConfig = {
  name: 'lcpgamecol',
  slug: 'lcpgamecolwapp',
  scheme: 'lcpgamecol',
  version: '1.0.0',
  orientation: 'portrait',
  icon: './assets/icon.png',
  // "automatic" lets the app follow the system light/dark setting.
  userInterfaceStyle: 'automatic',
  ios: {
    supportsTablet: true,
  },
  android: {
    adaptiveIcon: {
      backgroundColor: '#E6F4FE',
      foregroundImage: './assets/android-icon-foreground.png',
      backgroundImage: './assets/android-icon-background.png',
      monochromeImage: './assets/android-icon-monochrome.png',
    },
    predictiveBackGestureEnabled: false,
  },
  web: {
    bundler: 'metro',
    favicon: './assets/favicon.png',
  },
  plugins: [
    'expo-router',
    ['expo-localization', { supportedLocales: ['en', 'pt', 'de', 'fr', 'it', 'es', 'ja', 'hu'] }],
    'expo-secure-store',
    // Native splash shown before JS loads; matches the in-app splash (src/app/index.tsx)
    // and the theme background tokens (src/theme/tokens.ts).
    [
      'expo-splash-screen',
      {
        image: './assets/splash-icon.png',
        imageWidth: 128,
        resizeMode: 'contain',
        backgroundColor: '#f4f5ef',
        dark: { image: './assets/splash-icon.png', backgroundColor: '#151d1c' },
      },
    ],
    'expo-image',
  ],
  experiments: {
    typedRoutes: true,
  },
  extra: {
    apiUrl: process.env.EXPO_PUBLIC_API_URL,
  },
};

export default config;
