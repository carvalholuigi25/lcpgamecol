import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { I18nextProvider, useTranslation } from 'react-i18next';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { SessionProvider, useSession } from '@/auth';
import { i18n } from '@/i18n';
import { ThemeProvider, useTheme } from '@/theme';

// Auth screens draw their own frame (AuthLayout) with a "back to sign in" link.
const authScreenOptions = { headerShown: false } as const;

function ThemedStack() {
  const { t } = useTranslation();
  const { colors, scheme } = useTheme();
  const { status } = useSession();
  const signedIn = status === 'signedIn';
  return (
    <>
      <StatusBar style={scheme === 'dark' ? 'light' : 'dark'} />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: colors.surface },
          headerTintColor: colors.text,
          contentStyle: { backgroundColor: colors.background },
        }}
      >
        {/* Splash: no header, fades into the tabs or the sign-in screen. */}
        <Stack.Screen name="index" options={{ headerShown: false, animation: 'fade' }} />

        {/* Signed out (once the stored session has been checked): only the auth screens. */}
        <Stack.Protected guard={!signedIn} redirectTo="/home">
          <Stack.Screen name="login" options={{ ...authScreenOptions, animation: 'fade' }} />
          <Stack.Screen name="register" options={authScreenOptions} />
          <Stack.Screen name="forgot-password" options={authScreenOptions} />
        </Stack.Protected>

        {/* Signed in: the app itself. */}
        <Stack.Protected guard={signedIn} redirectTo="/login">
          <Stack.Screen name="(tabs)" options={{ headerShown: false, animation: 'fade' }} />
          <Stack.Screen name="games/index" options={{ title: t('Games') }} />
          <Stack.Screen name="games/[gameId]" options={{ title: t('Game details') }} />
          <Stack.Screen name="user/index" options={{ title: t('Users') }} />
          <Stack.Screen name="user/[userId]" options={{ title: t('Profile') }} />
        </Stack.Protected>
      </Stack>
    </>
  );
}

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <I18nextProvider i18n={i18n}>
        <ThemeProvider>
          <SessionProvider>
            <ThemedStack />
          </SessionProvider>
        </ThemeProvider>
      </I18nextProvider>
    </SafeAreaProvider>
  );
}
