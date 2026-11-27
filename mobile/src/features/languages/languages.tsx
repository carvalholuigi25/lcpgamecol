import { useTranslation } from 'react-i18next';
import { Text } from 'react-native';
import { languageNames, supportedLanguages, type Language } from '@/i18n';
import { useTheme } from '@/theme';
import { Dropdown, makeStyles } from '@/components';

function LanguagesFeature() {
  const { t, i18n } = useTranslation();
  const theme = useTheme();
  const styles = makeStyles(theme);

  return (
    <>
      <Text style={styles.label}>{t('Language')}</Text>
      <Dropdown
        label={t('Language')}
        value={i18n.language as Language}
        options={supportedLanguages.map((language: Language) => ({
          value: language,
          label: languageNames[language],
        }))}
        onChange={(language) => void i18n.changeLanguage(language)}
      />
    </>
  );
}

export { LanguagesFeature };
