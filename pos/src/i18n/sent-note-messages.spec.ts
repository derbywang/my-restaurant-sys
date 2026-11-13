import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const LANGUAGES = ['ja', 'zh', 'ko', 'en', 'fr'];

function words(language: string): { cart: Record<string, string>; errors: Record<string, string> } {
  return JSON.parse(readFileSync(join(__dirname, 'locales', `${language}.json`), 'utf8'));
}

describe('what is said about the note of a dish that was sent', () => {
  for (const language of LANGUAGES) {
    it(`is there in ${language}, and the one for those who may take dishes back says more`, () => {
      const { cart, errors } = words(language);
      expect(cart.sent_note_locked).toBeTruthy();
      expect(errors.sent_note_locked).toBeTruthy();
      expect(cart.sent_note_locked_reducer).toBeTruthy();
      expect(cart.sent_note_locked_reducer.startsWith(cart.sent_note_locked)).toBe(true);
      expect(cart.sent_note_locked_reducer.length).toBeGreaterThan(cart.sent_note_locked.length);
    });
  }

  it('in Japanese says what the store decided', () => {
    const { cart } = words('ja');
    expect(cart.sent_note_locked).toBe('厨房へ送信済みです。変更はキッチンに直接お伝えください。');
    expect(cart.sent_note_locked_reducer).toContain('変更する場合は、取り消してから追加し直してください');
  });
});

describe('what is said when the last line of a sent order is taken away', () => {
  for (const language of LANGUAGES) {
    it(`is there in ${language}`, () => {
      expect(words(language).cart.cannot_empty_sent_order).toBeTruthy();
    });
  }
});
