import { describe, expect, it } from 'vitest';

import en from '../i18n/locales/en.json';
import ja from '../i18n/locales/ja.json';
import ko from '../i18n/locales/ko.json';
import zh from '../i18n/locales/zh.json';
import { STAFF_ROLES, serverMessageOf, validateStaffAccount } from './staffAccount';

const ok = { first_name: '新人', login_id: 'shinjin@example.com', role: 'URY Cashier' };

describe('the roles a manager can give', () => {
  it('are the cashier, the waiter and the kitchen, and nothing that rules', () => {
    expect(STAFF_ROLES.map((r) => r.role)).toEqual(['URY Cashier', 'URY Captain', 'URY Kitchen']);
    expect(STAFF_ROLES.map((r) => r.role)).not.toContain('URY Manager');
  });
});

describe('what the form checks before it asks the server', () => {
  it('lets a good one through', () => {
    expect(validateStaffAccount(ok, ['URY Cashier', 'URY Captain', 'URY Kitchen'])).toBeNull();
  });

  it('wants a name', () => {
    expect(validateStaffAccount({ ...ok, first_name: '   ' }, ['URY Cashier'])).toBe('name_required');
  });

  it('wants a login ID that looks like an e-mail address (it need not exist)', () => {
    for (const login_id of ['', 'no-at-sign', 'has space@x.jp', '@x.jp', 'x@', 'a@b@c']) {
      expect(validateStaffAccount({ ...ok, login_id }, ['URY Cashier']), login_id).toBe('login_invalid');
    }
  });

  it('refuses a role the server did not offer', () => {
    expect(validateStaffAccount({ ...ok, role: 'URY Manager' }, ['URY Cashier', 'URY Captain'])).toBe('role_invalid');
    expect(validateStaffAccount({ ...ok, role: 'URY Kitchen' }, ['URY Cashier'])).toBe('role_invalid');
  });
});

describe('the words of the server in a refusal', () => {
  it('takes the last message the server sent, without its HTML', () => {
    const err = { _server_messages: JSON.stringify([JSON.stringify({ message: '<b>There is already</b> an account.' })]) };
    expect(serverMessageOf(err)).toBe('There is already an account.');
  });

  it('is empty when there is nothing to take (the page then says its own words)', () => {
    expect(serverMessageOf({})).toBe('');
    expect(serverMessageOf({ _server_messages: 'not json' })).toBe('');
    expect(serverMessageOf(null)).toBe('');
  });
});

describe('the words of the page that makes an account', () => {
  const locales = { ja, en, zh, ko } as unknown as Record<string, { staff_account?: Record<string, string> }>;

  it('are in every language, with the same keys', () => {
    const keys = Object.keys(locales.ja.staff_account ?? {}).sort();
    expect(keys.length).toBeGreaterThan(10);
    for (const [name, locale] of Object.entries(locales)) {
      expect(Object.keys(locale.staff_account ?? {}).sort(), name).toEqual(keys);
      for (const key of keys) expect(locale.staff_account?.[key], `${name}.${key}`).toBeTruthy();
    }
  });

  it('say that the password is shown only this once (a manager must write it down)', () => {
    expect(locales.ja.staff_account?.password_once).toContain('一度だけ');
    expect(locales.ja.staff_account?.password_once).toContain('閉じる');
  });

  it('name the three roles in the staff\'s own words', () => {
    expect([locales.ja.staff_account?.role_cashier, locales.ja.staff_account?.role_captain, locales.ja.staff_account?.role_kitchen]).toEqual(['レジ担当', 'ホール', '厨房']);
  });
});
