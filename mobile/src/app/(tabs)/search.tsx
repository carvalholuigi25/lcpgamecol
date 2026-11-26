import { useTranslation } from 'react-i18next';
import { Text } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { makeStyles } from '@/components';
import { useTheme } from '@/theme';

export default function SearchScreen() {
  const { t } = useTranslation();
  const styles = makeStyles(useTheme());

  return (
    <SafeAreaView style={[styles.screen, styles.centered]} edges={['top']}>
      <Text style={styles.title}>{t('Search')}</Text>
      <Text style={styles.muted}>{t('Coming soon')}</Text>
    </SafeAreaView>
  );
}
