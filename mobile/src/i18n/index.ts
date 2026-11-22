import { getLocales } from 'expo-localization';
import { createInstance, type i18n as I18n } from 'i18next';
import { initReactI18next } from 'react-i18next';

// The same dictionaries the web pages use (repo root locales/<lang>.json). Keys are the
// English text, so English needs no dictionary and a missing key shows the English text.
import de from '../../../locales/de.json';
import en from '../../../locales/en.json';
import es from '../../../locales/es.json';
import fr from '../../../locales/fr.json';
import hu from '../../../locales/hu.json';
import it from '../../../locales/it.json';
import ja from '../../../locales/ja.json';
import pt from '../../../locales/pt.json';

const dictionaries = { en, pt, de, fr, it, es, ja, hu } as const;

export type Language = keyof typeof dictionaries;

export const languageNames: Record<Language, string> = {
  en: 'English',
  pt: 'Português',
  de: 'Deutsch',
  fr: 'Français',
  it: 'Italiano',
  es: 'Español',
  ja: '日本語',
  hu: 'Magyar',
};

export const supportedLanguages = Object.keys(dictionaries) as Language[];

export function isSupportedLanguage(value: string | null | undefined): value is Language {
  return !!value && Object.hasOwn(dictionaries, value);
}

/** The first of the device's preferred languages that the app supports, else English. */
export function deviceLanguage(
  locales: { languageCode: string | null }[] = safeGetLocales(),
): Language {
  for (const { languageCode } of locales) {
    const code = languageCode?.toLowerCase();
    if (isSupportedLanguage(code)) return code;
  }
  return 'en';
}

function safeGetLocales() {
  try {
    return getLocales();
  } catch {
    return [];
  }
}

export function createI18n(language: Language = deviceLanguage()): I18n {
  const instance = createInstance();
  void instance.use(initReactI18next).init({
    lng: language,
    fallbackLng: 'en',
    resources: Object.fromEntries(
      Object.entries(dictionaries).map(([code, messages]) => [code, { translation: messages }]),
    ),
    // English sentences are the keys: they contain "." and ":".
    keySeparator: false,
    nsSeparator: false,
    // The shared strings use {name} placeholders, not i18next's default {{name}}.
    interpolation: { prefix: '{', suffix: '}', escapeValue: false },
    returnNull: false,
    returnEmptyString: false,
    initAsync: false,
  });
  return instance;
}

export const i18n = createI18n();
