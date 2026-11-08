import { describe, expect, it } from 'vitest';
import de from './locales/fr.json';
import en from './locales/en.json';
import ja from './locales/ja.json';
import ko from './locales/ko.json';
import zh from './locales/zh.json';

// 会計合算 keeps one bill and takes the other into it: the message says which went into which.
describe('the message after merging two bills', () => {
  const all = { fr: de, en, ja, ko, zh } as Record<string, { bill_merge: { merge_success: string } }>;

  it.each(Object.keys(all))('%s names both bills', (lang) => {
    const text = all[lang].bill_merge.merge_success;
    expect(text).toContain('{{invoice}}');
    expect(text).toContain('{{other}}');
  });

  it('ja says the second bill went into the first', () => {
    expect(ja.bill_merge.merge_success).toBe('伝票 {{other}} を {{invoice}} に合算しました');
  });
});
