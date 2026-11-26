import { Link } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useSession } from '@/auth';
import { Chip, makeStyles } from '@/components';
import { isAdmin } from '@/features/users';
import { useTheme } from '@/theme';

// Main screen the splash hands over to.
export default function HomeScreen() {
  const { t } = useTranslation();
  const styles = makeStyles(useTheme());
  const { user } = useSession();

  return (
    <SafeAreaView style={styles.screen} edges={['top']}>
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.heading}>{t('Game Shelf')}</Text>
        <Text style={styles.muted}>{t('Your collection')}</Text>

        <View style={styles.row}>
          <Link href="/games" asChild>
            <Chip label={t('Games')} styles={styles} />
          </Link>
          <Link href="/user" asChild>
            <Chip label={isAdmin(user) ? t('Users') : t('Community')} styles={styles} />
          </Link>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
