import { getActiveLanguage, initI18n as initSharedI18n } from '@ury/core'
import { useSyncExternalStore } from 'react'

// The engine is in @ury/core; the words of the ordering page are in ./locales. The page starts in the language of the
// store and is set to the language of the session (the guest's choice, or the profile's default) once that is known.
export { t, tOr } from '@ury/core'

const LOCALES = import.meta.glob('./locales/*.json')
const DEFAULT = 'ja'

/** The pack of this language: its own (zh-TW), else the language alone (zh); none: undefined (the engine falls back to English). */
function packFor(lang: string): string | undefined {
  const has = (code: string) => `./locales/${code}.json` in LOCALES
  return [lang, lang.split('-')[0]].find(has)
}

export function initI18n(lang = DEFAULT): Promise<void> {
  const code = packFor(lang) ?? lang
  return initSharedI18n({ locales: LOCALES, lang: code })
}

const listeners = new Set<() => void>()

/** Switch the words of the page, tell what shows them, and say the language to the browser. */
export async function setLanguage(lang: string): Promise<void> {
  await initI18n(lang)
  if (typeof document !== 'undefined') document.documentElement.lang = lang
  listeners.forEach((listener) => listener())
}

export function subscribeLanguage(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** The language the words are in now; a component that uses it is drawn again when the language changes. */
export function useLanguage(): string {
  return useSyncExternalStore(subscribeLanguage, getActiveLanguage)
}
