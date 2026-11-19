import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

import ja from '../i18n/locales/ja.json';
import en from '../i18n/locales/en.json';
import ko from '../i18n/locales/ko.json';
import zh from '../i18n/locales/zh.json';

// 2026-11-19: the page asked for get_staff_account_options with call(...) which is a POST, and the server only answers a GET
// (403): the error was swallowed, and the page looked as it did before ("no button, no hint"). The way the page calls each
// function must be the way the server declares it.
const root = resolve(__dirname, '../../..');
const server = readFileSync(resolve(root, 'ury/ury/api/staff_accounts.py'), 'utf8');
const page = readFileSync(resolve(__dirname, '../pages/Dashboard/UserPage.tsx'), 'utf8');

function declaredMethods(): Record<string, string> {
  const found: Record<string, string> = {};
  const re = /@frappe\.whitelist\(methods=\["(\w+)"\]\)\s*\n\s*def (\w+)/g;
  for (const m of server.matchAll(re)) found[m[2]] = m[1];
  return found;
}

function calledAs(fn: string): string[] {
  const re = new RegExp(`call(\\.(get|post|put|delete))?\\(\\s*'ury\\.ury\\.api\\.staff_accounts\\.${fn}'`, 'g');
  // call(path) alone is a POST (packages/core/src/frappe/client.ts)
  return [...page.matchAll(re)].map((m) => (m[2] ?? 'post').toUpperCase());
}

describe('the page calls the staff account functions the way the server declares them', () => {
  const declared = declaredMethods();

  it('finds both functions on the server', () => {
    expect(Object.keys(declared).sort()).toEqual(['create_staff_account', 'get_staff_account_options']);
  });

  for (const fn of ['create_staff_account', 'get_staff_account_options']) {
    it(`${fn}: the page uses ${declared[fn]}`, () => {
      const used = calledAs(fn);
      expect(used.length).toBeGreaterThan(0);
      for (const method of used) expect(method).toBe(declared[fn]);
    });
  }

  it('does not hide a failed options call: the page says so', () => {
    expect(page).toContain('staff_account.options_failed');
  });

  it('has the text for it in the four languages', () => {
    for (const locale of [en, ja, ko, zh]) {
      expect((locale as any).staff_account.options_failed).toBeTruthy();
    }
    expect((ja as any).staff_account.options_failed).toContain('アカウントを作る');
  });
});
