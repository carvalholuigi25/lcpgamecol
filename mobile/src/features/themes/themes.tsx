import { useTranslation } from 'react-i18next';
import { Text } from 'react-native';

import { useTheme, useThemeSettings, type ThemePreference } from '@/theme';
import { Dropdown, makeStyles } from '@/components';

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
      <Dropdown
        label={t('Theme')}
        value={preference}
        options={themeOptions.map((option) => ({ value: option.value, label: t(option.label) }))}
        onChange={setPreference}
      />
    </>
  );
}

export { ThemesFeature };
