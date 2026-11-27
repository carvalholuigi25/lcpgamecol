import { createI18n, deviceLanguage, supportedLanguages } from './index';

describe('deviceLanguage', () => {
  it('picks the first supported preferred language', () => {
    expect(deviceLanguage([{ languageCode: 'pl' }, { languageCode: 'JA' }])).toBe('ja');
  });

  it('falls back to English', () => {
    expect(deviceLanguage([{ languageCode: 'pl' }, { languageCode: null }])).toBe('en');
    expect(deviceLanguage([])).toBe('en');
  });
});

describe('shared translations', () => {
  it('loads every language from locales/', () => {
    expect(supportedLanguages).toEqual(['en', 'pt', 'de', 'fr', 'it', 'es', 'ja', 'hu']);
  });

  it('translates English source strings', () => {
    const i18n = createI18n('hu');
    expect(i18n.t('Sign in')).toBe('Bejelentkezés');
    i18n.changeLanguage('it');
    expect(i18n.t('Buy now')).toBe('Acquista ora');
  });

  it('uses the web {name} placeholders', () => {
    const i18n = createI18n('pt');
    expect(
      i18n.t('Showing the first {count} matches. Refine your search to see more.', { count: 5 }),
    ).toBe('A mostrar as primeiras 5 correspondências. Refine a pesquisa para ver mais.');
  });

  it('shows the English text for English and for missing keys', () => {
    expect(createI18n('en').t('Sign in')).toBe('Sign in');
    expect(createI18n('ja').t('A sentence nobody translated.')).toBe(
      'A sentence nobody translated.',
    );
  });
});
