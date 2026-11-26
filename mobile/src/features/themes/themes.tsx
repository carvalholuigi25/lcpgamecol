import { useTranslation } from 'react-i18next';
import { Text, View } from 'react-native';

import { useTheme, useThemeSettings, type ThemePreference } from '@/theme';
import { Chip, makeStyles } from '@/components';

const themeOptions: { value: ThemePreference; label: string }[] = [
  { value: 'system', label: 'Auto' },
  { value: 'light', label: 'White' },
  { value: 'dark', label: 'Dark' },
];

function ThemesFeature() {
  const { t } = useTranslation();
  const theme = useTheme();
  const { preference, setPreference } = useThemeSettings();
  const styles = makeStyles(theme);

  return (
    <>
      <Text style={styles.label}>{t('Theme')}</Text>
      <View style={styles.row}>
        {themeOptions.map((option) => (
          <Chip
            key={option.value}
            label={t(option.label)}
            selected={preference === option.value}
            onPress={() => setPreference(option.value)}
            styles={styles}
          />
        ))}
      </View>
    </>
  );
}

export { ThemesFeature };
