export const DEFAULT_LANGUAGE = 'en';

export const SUPPORTED_LANGUAGES: Record<string, string> = {
  en: 'English',
  ja: '日本語',
  zh: '中文',
  ko: '한국어',
  fr: 'Français',
  ar: 'العربية',
};

/**
 * Languages offered in the staff language menu, in display order. fr / ar
 * keep their locale files in pos but are not offered. Must match
 * STAFF_LANGUAGES in ury/ury/api/language.py, which is the list the server accepts.
 */
export const MENU_LANGUAGES: Record<string, string> = {
  ja: SUPPORTED_LANGUAGES.ja,
  zh: SUPPORTED_LANGUAGES.zh,
  ko: SUPPORTED_LANGUAGES.ko,
  en: SUPPORTED_LANGUAGES.en,
};
