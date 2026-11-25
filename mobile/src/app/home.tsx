import { Stack } from 'expo-router';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { api, ApiError, NetworkError, type Schemas } from '@/api';
import { languageNames, supportedLanguages, type Language } from '@/i18n';
import { useTheme, useThemeSettings, type ThemePreference } from '@/theme';
import { useNavigation } from '@react-navigation/native';

type Status =
  | { state: 'loading' }
  | { state: 'ok'; config: Schemas['ClientConfig'] }
  | { state: 'error'; message: string };

const themeOptions: { value: ThemePreference; label: string }[] = [
  { value: 'system', label: 'Auto' },
  { value: 'light', label: 'White' },
  { value: 'dark', label: 'Dark' },
];

// Placeholder start screen for the project setup phase: shows that the API client,
// theme and translations are wired up. The library replaces it in Phase 3.
export default function HomeScreen() {
  const { t, i18n } = useTranslation();
  const theme = useTheme();
  const { preference, setPreference } = useThemeSettings();
  const [status, setStatus] = useState<Status>({ state: 'loading' });
  const styles = makeStyles(theme);
  const navigation: any = useNavigation();

  useEffect(() => {
    const controller = new AbortController();
    api
      .get<Schemas['ClientConfig']>('/client/config', { auth: false, signal: controller.signal })
      .then((config) => setStatus({ state: 'ok', config }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message =
          error instanceof ApiError || error instanceof NetworkError
            ? error.message
            : String(error);
        setStatus({ state: 'error', message });
      });
    return () => controller.abort();
  }, []);

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Stack.Screen options={{ title: t('Game Shelf') }} />

      <Text style={styles.heading}>{t('Your collection')}</Text>
      <Text style={styles.muted} testID="api-status">
        {status.state === 'loading' && `${api.baseUrl} …`}
        {status.state === 'ok' && `${api.baseUrl} · API v${status.config.api_version}`}
        {status.state === 'error' && `${api.baseUrl} · ${status.message}`}
      </Text>

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

      <View style={styles.row}>
        <Chip
          key="games"
          label="Games"
          selected={false}
          onPress={() => {
            navigation.navigate('Games');
          }}
          styles={styles}
        />
      </View>
    </ScrollView>
  );
}

function Chip({
  label,
  selected,
  onPress,
  styles,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
  styles: ReturnType<typeof makeStyles>;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[styles.chip, selected && styles.chipSelected]}
    >
      <Text style={[styles.chipText, selected && styles.chipTextSelected]}>{label}</Text>
    </Pressable>
  );
}

function makeStyles({ colors, spacing, radius, typography }: ReturnType<typeof useTheme>) {
  return StyleSheet.create({
    container: { padding: spacing.lg, gap: spacing.md },
    heading: { ...typography.display, color: colors.text },
    muted: { ...typography.caption, color: colors.muted },
    label: { ...typography.label, color: colors.text, marginTop: spacing.md },
    row: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
    chip: {
      paddingVertical: spacing.xs + 2,
      paddingHorizontal: spacing.md,
      borderRadius: radius.pill,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.surface,
    },
    chipSelected: { backgroundColor: colors.primary, borderColor: colors.primary },
    chipText: { ...typography.label, color: colors.text },
    chipTextSelected: { color: colors.onPrimary },
  });
}
