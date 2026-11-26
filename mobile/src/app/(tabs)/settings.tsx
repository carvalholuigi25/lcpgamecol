import { router } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useSession } from '@/auth';
import { Button, makeStyles } from '@/components';
import { LanguagesFeature, ThemesFeature } from '@/features';
import { useTheme } from '@/theme';

export default function SettingsScreen() {
  const { t } = useTranslation();
  const theme = useTheme();
  const styles = makeStyles(theme);
  const { user, signOut } = useSession();
  const [signingOut, setSigningOut] = useState(false);

  async function handleSignOut() {
    setSigningOut(true);
    try {
      // The route guards in _layout.tsx send the user to /login afterwards.
      await signOut();
    } finally {
      setSigningOut(false);
    }
  }

  return (
    <SafeAreaView style={styles.screen} edges={['top']}>
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.heading}>{t('Settings')}</Text>
        <ThemesFeature />
        <LanguagesFeature />

        <Text style={styles.label}>{t('Account')}</Text>
        <View style={{ gap: theme.spacing.sm }}>
          <Text style={styles.body}>
            {user ? t('Signed in as {name}', { name: user.username }) : t('Signed in')}
          </Text>
          {user ? (
            <Button
              variant="link"
              label={t('View my profile')}
              onPress={() =>
                router.push({ pathname: '/user/[userId]', params: { userId: user.username } })
              }
            />
          ) : null}
          <Button label={t('Sign out')} onPress={() => void handleSignOut()} loading={signingOut} />
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
