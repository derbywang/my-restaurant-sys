import { describe, expect, it } from 'vitest';
import en from './locales/en.json';
import ja from './locales/ja.json';
import ko from './locales/ko.json';
import zh from './locales/zh.json';
import { ATTENTION_TYPES, attentionMessage } from '../lib/attention';

type Locale = { dashboard: { attention: Record<string, string> } };

describe('the lines of "needs attention" on the manager home', () => {
  it('have a text with the count in ja, zh, ko and en for every kind', () => {
    for (const locale of [ja, zh, ko, en] as unknown as Locale[]) {
      for (const kind of ATTENTION_TYPES) {
        expect(locale.dashboard.attention[kind], kind).toContain('{{count}}');
      }
    }
  });

  it('are not English in ja, zh and ko', () => {
    for (const locale of [ja, zh, ko] as unknown as Locale[]) {
      for (const kind of ATTENTION_TYPES) {
        expect(locale.dashboard.attention[kind], kind).not.toMatch(/\b(table|order|session|issue)\(?s?\)?\b/i);
      }
    }
  });

  it('are translated from the kind and the count, not from the server text', () => {
    const t = (key: string, options?: { count?: number }) => `<${key}:${options?.count}>`;
    const item = { type: 'table_occupied_long', count: 4, message: '4 table(s) occupied for over 60 minutes' };
    expect(attentionMessage(item, t)).toBe('<dashboard.attention.table_occupied_long:4>');
  });

  it('keep the server text for a kind it does not know', () => {
    const t = (key: string) => key;
    expect(attentionMessage({ type: 'something_new', count: 1, message: 'Something new' }, t)).toBe('Something new');
  });
});
