import { initI18n as initSharedI18n } from '@ury/core'

// The engine is in @ury/core; the words of the ordering page are in ./locales. Until the profile's
// default language is read (i18n phase B) the page speaks the language of the store.
export { t, tOr } from '@ury/core'

export function initI18n(lang = 'ja'): Promise<void> {
  return initSharedI18n({ locales: import.meta.glob('./locales/*.json'), lang })
}
