// The manager makes the accounts of the staff (ury/ury/api/staff_accounts.py). What the form checks before it asks, and the words of a refusal.

/** The roles a manager can give: the server offers exactly these (a manager, a URY Admin or a System Manager cannot be made here). */
export const STAFF_ROLES = [
  { role: 'URY Cashier', key: 'cashier' },
  { role: 'URY Captain', key: 'captain' },
  { role: 'URY Kitchen', key: 'kitchen' },
] as const;

export interface StaffAccountForm {
  first_name: string;
  login_id: string;
  role: string;
}

export type StaffFormError = 'name_required' | 'login_invalid' | 'role_invalid';

const LOGIN_ID = /^[^@\s]+@[^@\s]+$/;

export function validateStaffAccount(form: StaffAccountForm, allowedRoles: readonly string[]): StaffFormError | null {
  if (!form.first_name.trim()) return 'name_required';
  if (!LOGIN_ID.test(form.login_id.trim())) return 'login_invalid';
  if (!allowedRoles.includes(form.role)) return 'role_invalid';
  return null;
}

/** The last message the server sent with an error, without its HTML; '' when there is none (the page then says its own words). */
export function serverMessageOf(err: unknown): string {
  const raw = (err as { _server_messages?: unknown } | null)?._server_messages;
  if (typeof raw !== 'string') return '';
  try {
    const list = JSON.parse(raw) as unknown[];
    const last = list[list.length - 1];
    const message = typeof last === 'string' ? JSON.parse(last) : last;
    return typeof message?.message === 'string' ? message.message.replace(/<[^>]*>/g, '') : '';
  } catch {
    return '';
  }
}
