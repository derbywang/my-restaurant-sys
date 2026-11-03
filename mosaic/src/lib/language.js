// The language of the screen: the language of the logged-in user, which `get_site_name` tells.
// The words are in ./i18n.js; templates use `$t('key')`, scripts import `t`.
import { reactive } from "vue";
import { DEFAULT_LANGUAGE, hasMessage, localeOf, normalizeLanguage, translate } from "./i18n.js";

const state = reactive({ lang: DEFAULT_LANGUAGE });

export const t = (key, params) => translate(state.lang, key, params);

/** The translation of `key`, or `fallback` when there is none (the type of a ticket comes from the server). */
export const tOr = (key, fallback) => (hasMessage(state.lang, key) ? t(key) : fallback);

/** The clock in the way the language writes it. */
export const timeNow = (date = new Date()) => date.toLocaleTimeString(localeOf(state.lang));

export function setLanguage(code) {
  state.lang = normalizeLanguage(code);
  document.documentElement.lang = state.lang; // the right glyphs of the Chinese characters
  document.title = t("app.title");
}

/** Ask the server for the language of the user; keeps Japanese when it cannot be reached. */
export async function initLanguage() {
  setLanguage(DEFAULT_LANGUAGE);
  try {
    const response = await fetch("/api/method/ury.ury.api.ury_kot_display.get_site_name");
    const data = await response.json();
    setLanguage(data?.message?.lang);
  } catch (error) {
    console.error("Failed to fetch the language:", error);
  }
}

export function installLanguage(app) {
  app.config.globalProperties.$t = t;
  app.config.globalProperties.$tOr = tOr;
}
