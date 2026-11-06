import { describe, expect, it } from 'vitest';
import en from './locales/en.json';
import fr from './locales/fr.json';
import ja from './locales/ja.json';
import ko from './locales/ko.json';
import zh from './locales/zh.json';
import { openOrderError } from '../lib/pos-permissions';

describe('the message when an order cannot be opened', () => {
  it('exists in every staff language', () => {
    for (const locale of [ja, zh, ko, en, fr]) {
      expect((locale as unknown as { errors: Record<string, string> }).errors.not_permitted_order).toBeTruthy();
    }
  });

  it('replaces the English text of a permission error and leaves other errors alone', () => {
    const t = (key: string) => `<${key}>`;
    const refused = { exc_type: 'PermissionError', message: 'Not permitted to view this order' };
    expect(openOrderError(refused, 'fallback', t)).toBe('<errors.not_permitted_order>');
    expect(openOrderError(new Error('boom'), 'fallback', t)).toBe('boom');
  });
});
