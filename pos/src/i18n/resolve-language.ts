import { DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES } from './config';

/**
 * Resolves the active language from `frappe.boot.lang` (the logged-in user's
 * User.language, set by `set_staff_language`). Falls back to DEFAULT_LANGUAGE
 * ('en') when boot is unavailable or the language has no locale file.
 *
 * No client-side override is read: the language is stored per user on the
 * server, so it follows the account across devices.
 */
export function resolveLanguage(): string {
  const frappeLang = (window as { frappe?: { boot?: { lang?: string } } }).frappe?.boot?.lang;
  if (frappeLang && SUPPORTED_LANGUAGES[frappeLang]) {
    return frappeLang;
  }

  return DEFAULT_LANGUAGE;
}
