import { call } from './client';

/**
 * Save the language of the logged-in user (User.language) via the server and
 * reload the page so `frappe.boot.lang` picks it up. Rejects on failure so the
 * caller can show an error.
 */
export async function setStaffLanguage(lang: string): Promise<void> {
  await call.post('ury.ury.api.language.set_staff_language', { lang });
  window.location.reload();
}
