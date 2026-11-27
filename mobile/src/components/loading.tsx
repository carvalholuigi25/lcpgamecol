import { ActivityIndicator, Text, View } from 'react-native';

import { useTheme } from '@/theme';

import { makeStyles } from './styles';

/** Full-screen themed spinner with an optional caption. */
export function Loading({ label }: { label?: string }) {
  const theme = useTheme();
  const styles = makeStyles(theme);
  return (
    <View style={[styles.screen, styles.centered]}>
      <ActivityIndicator size="large" color={theme.colors.primary} />
      {label ? <Text style={styles.muted}>{label}</Text> : null}
    </View>
  );
}
