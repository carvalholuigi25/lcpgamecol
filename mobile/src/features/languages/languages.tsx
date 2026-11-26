import { useTranslation } from 'react-i18next';
import { Text, View } from 'react-native';
import { languageNames, supportedLanguages, type Language } from '@/i18n';
import { useTheme } from '@/theme';
import { Chip, makeStyles } from '@/components';

function LanguagesFeature() {
  const { t, i18n } = useTranslation();
  const theme = useTheme();
  const styles = makeStyles(theme);

  return (
    <>
      <Text style={styles.label}>{t('Language')}</Text>
      <View style={styles.row}>
        {supportedLanguages.map((language: Language) => (
          <Chip
            key={language}
            label={languageNames[language]}
            selected={i18n.language === language}
            onPress={() => void i18n.changeLanguage(language)}
            styles={styles}
          />
        ))}
      </View>
    </>
  );
}

export { LanguagesFeature };
