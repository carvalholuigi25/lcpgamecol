import Constants from 'expo-constants';
import * as Updates from 'expo-updates';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Platform, Text, View } from 'react-native';

import { Button, makeStyles } from '@/components';
import { useTheme } from '@/theme';

type Status =
  | { kind: 'idle' }
  | { kind: 'checking' }
  | { kind: 'downloading' }
  | { kind: 'upToDate' }
  | { kind: 'ready' }
  | { kind: 'error' };

// Update checks only work in release builds with expo-updates set up. Dev mode,
// Expo Go and web reject the calls, so we hide the button there.
const updatesSupported = Platform.OS !== 'web' && !__DEV__ && Updates.isEnabled;

function UpdatesFeature() {
  const { t } = useTranslation();
  const theme = useTheme();
  const styles = makeStyles(theme);
  const [status, setStatus] = useState<Status>({ kind: 'idle' });

  const appVersion = Constants.expoConfig?.version ?? '—';
  const updateLabel = Updates.isEmbeddedLaunch
    ? t('Built-in')
    : (Updates.createdAt?.toLocaleDateString() ?? (Updates.updateId?.slice(0, 8) || '—'));

  async function handleCheck() {
    setStatus({ kind: 'checking' });
    try {
      const check = await Updates.checkForUpdateAsync();
      if (!check.isAvailable && !check.isRollBackToEmbedded) {
        setStatus({ kind: 'upToDate' });
        return;
      }
      setStatus({ kind: 'downloading' });
      const fetched = await Updates.fetchUpdateAsync();
      if (fetched.isNew || fetched.isRollBackToEmbedded) {
        setStatus({ kind: 'ready' });
      } else {
        setStatus({ kind: 'upToDate' });
      }
    } catch {
      setStatus({ kind: 'error' });
    }
  }

  const busy = status.kind === 'checking' || status.kind === 'downloading';
  const message: Record<Status['kind'], string | null> = {
    idle: null,
    checking: t('Checking for updates...'),
    downloading: t('Downloading update...'),
    upToDate: t('You are on the latest version.'),
    ready: t('Update downloaded. Restart the app to apply it.'),
    error: t('Could not check for updates. Try again later.'),
  };

  return (
    <>
      <Text style={styles.label}>{t('App updates')}</Text>
      <View style={{ gap: theme.spacing.sm }}>
        <Text style={styles.body}>{t('Version {version}', { version: appVersion })}</Text>
        {updatesSupported ? (
          <>
            <Text style={styles.muted}>{t('Update: {update}', { update: updateLabel })}</Text>
            {message[status.kind] ? <Text style={styles.muted}>{message[status.kind]}</Text> : null}
            {status.kind === 'ready' ? (
              <Button label={t('Restart now')} onPress={() => void Updates.reloadAsync()} />
            ) : (
              <Button
                label={t('Check for updates')}
                onPress={() => void handleCheck()}
                loading={busy}
              />
            )}
          </>
        ) : (
          <Text style={styles.muted}>{t('Updates are not available in this build.')}</Text>
        )}
      </View>
    </>
  );
}

export { UpdatesFeature };
