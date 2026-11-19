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

/** What the server says (its English) -> the key of the words of the page (`staff_account.<key>`). Each message of
 *  ury/ury/api/staff_accounts.py is here; a test reads that file and fails when one is missing. */
const SERVER_MESSAGES: Array<[string, string]> = [
  ['Not permitted', 'not_permitted'],
  ['You are not in any branch', 'no_branch'],
  ['Please write the name', 'name_required'],
  ['The login ID has the form of an e-mail address', 'login_invalid'],
  ['Only a cashier, a waiter or the kitchen can be made here', 'role_invalid'],
  ['Say which branch the account is for', 'branch_required'],
  ['This is not your branch', 'branch_not_yours'],
  ['There is already an account with this login ID', 'duplicate'],
  ['The account could not be made', 'failed'],
];

/** The key of the page's own words for a refusal of the server; '' when the message is not one it knows. */
export function serverErrorKeyOf(err: unknown): string {
  const message = serverMessageOf(err);
  return SERVER_MESSAGES.find(([english]) => message.startsWith(english))?.[1] ?? '';
}
