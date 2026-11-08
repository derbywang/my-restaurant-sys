import { describe, expect, it } from 'vitest';

import { answerIsYes } from './permission';

describe('answerIsYes', () => {
  it('is a yes only for has_permission === true, wrapped or not', () => {
    expect(answerIsYes({ has_permission: true })).toBe(true);
    expect(answerIsYes({ message: { has_permission: true } })).toBe(true);
  });

  it('is a no for everything else', () => {
    expect(answerIsYes({ has_permission: false })).toBe(false);
    expect(answerIsYes({ message: { has_permission: false } })).toBe(false);
    expect(answerIsYes({ has_permission: 1 })).toBe(false);
    expect(answerIsYes({ has_permission: 'yes' })).toBe(false);
    expect(answerIsYes(null)).toBe(false);
    expect(answerIsYes(undefined)).toBe(false);
    expect(answerIsYes({})).toBe(false);
    expect(answerIsYes(true)).toBe(false);
  });
});
