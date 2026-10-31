import { initI18n as initSharedI18n } from '@ury/core';

// The i18n engine lives in @ury/core; the locale files stay in this app.
export {
  t,
  tOr,
  getActiveLanguage,
  getActiveDirection,
  applyDocumentLocale,
  resolveLanguage,
  DEFAULT_LANGUAGE,
  SUPPORTED_LANGUAGES,
  MENU_LANGUAGES,
} from '@ury/core';

export function initI18n(lang?: string): Promise<void> {
  return initSharedI18n({ locales: import.meta.glob('./locales/*.json'), lang });
}
