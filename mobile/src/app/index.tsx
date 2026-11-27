import { router, type Href } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ActivityIndicator,
  Animated,
  Image,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { api, ApiError, NetworkError, setAssetBaseUrl, type Schemas } from '@/api';
import { useSession } from '@/auth';
import { useTheme } from '@/theme';

/** Where the splash hands over to once the app is ready. */
const MAIN_ROUTE: Href = '/home';
const LOGIN_ROUTE: Href = '/login';
/** Keep the splash up at least this long so it doesn't just flash. */
const MIN_SPLASH_MS = 1200;

type Status = { state: 'loading' } | { state: 'ready' } | { state: 'error'; message: string };

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

// Splash screen (entry route "/"): shows the logo while the client config loads and the
// stored session is restored, then replaces itself with the main screen (signed in) or
// the sign-in screen, so "back" can't return to it.
export default function SplashScreen() {
  const { t } = useTranslation();
  const theme = useTheme();
  const styles = makeStyles(theme);
  const session = useSession();
  const [status, setStatus] = useState<Status>({ state: 'loading' });
  const [attempt, setAttempt] = useState(0);
  const [fade] = useState(() => new Animated.Value(0));

  useEffect(() => {
    Animated.timing(fade, {
      toValue: 1,
      duration: 500,
      useNativeDriver: Platform.OS !== 'web',
    }).start();
  }, [fade]);

  useEffect(() => {
    const controller = new AbortController();

    Promise.all([
      api.get<Schemas['ClientConfig']>('/client/config', {
        auth: false,
        signal: controller.signal,
      }),
      wait(MIN_SPLASH_MS),
    ])
      .then(([config]) => {
        if (controller.signal.aborted) return;
        setAssetBaseUrl(config.asset_base_url);
        setStatus({ state: 'ready' });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message =
          error instanceof ApiError || error instanceof NetworkError
            ? error.message
            : String(error);
        setStatus({ state: 'error', message });
      });

    return () => controller.abort();
  }, [attempt]);

  // Hand over once both the config and the session check are done.
  useEffect(() => {
    if (status.state !== 'ready' || session.status === 'loading') return;
    router.replace(session.status === 'signedIn' ? MAIN_ROUTE : LOGIN_ROUTE);
  }, [status.state, session.status]);

  const retry = useCallback(() => {
    setStatus({ state: 'loading' });
    setAttempt((n) => n + 1);
  }, []);

  return (
    <View style={styles.container}>
      <Animated.View style={[styles.brand, { opacity: fade }]}>
        <Image
          source={require('../../assets/splash-icon.png')}
          style={styles.logo}
          resizeMode="contain"
          accessibilityIgnoresInvertColors
        />
        <Text style={styles.heading}>{t('Game Shelf')}</Text>
        <Text style={styles.muted}>{t('Your collection')}</Text>
      </Animated.View>

      <View style={styles.footer} testID="api-status">
        {status.state !== 'error' ? (
          <>
            <ActivityIndicator size="large" color={theme.colors.primary} />
            <Text style={styles.muted}>{t('Loading…')}</Text>
          </>
        ) : (
          <>
            <Text style={styles.error}>{t('Could not reach the server.')}</Text>
            <Text style={styles.muted}>{status.message}</Text>
            <Pressable accessibilityRole="button" onPress={retry} style={styles.button}>
              <Text style={styles.buttonText}>{t('Try again')}</Text>
            </Pressable>
          </>
        )}
      </View>
    </View>
  );
}

function makeStyles({ colors, spacing, radius, typography }: ReturnType<typeof useTheme>) {
  return StyleSheet.create({
    container: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      padding: spacing.xl,
      backgroundColor: colors.background,
    },
    brand: { alignItems: 'center', gap: spacing.sm },
    logo: { width: 128, height: 128, marginBottom: spacing.md },
    heading: { ...typography.display, color: colors.text },
    muted: { ...typography.caption, color: colors.muted, textAlign: 'center' },
    error: { ...typography.body, color: colors.danger, textAlign: 'center' },
    footer: {
      position: 'absolute',
      bottom: spacing.xxl * 2,
      left: spacing.xl,
      right: spacing.xl,
      alignItems: 'center',
      gap: spacing.sm,
    },
    button: {
      marginTop: spacing.sm,
      paddingVertical: spacing.sm,
      paddingHorizontal: spacing.xl,
      borderRadius: radius.pill,
      backgroundColor: colors.primary,
    },
    buttonText: { ...typography.label, color: colors.onPrimary },
  });
}
