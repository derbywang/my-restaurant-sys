import { describe, expect, it } from 'vitest';
import { blockedYenKey, wholeYen } from './yen-input';

describe('wholeYen (a yen amount typed into the opening and closing screens)', () => {
  it('reads a whole number', () => {
    expect(wholeYen('10000')).toBe(10000);
  });

  it('is 0 for empty or not a number', () => {
    expect(wholeYen('')).toBe(0);
    expect(wholeYen('abc')).toBe(0);
  });

  it('drops decimals: yen has none', () => {
    expect(wholeYen('1000.5')).toBe(1000);
    expect(wholeYen('0.99')).toBe(0);
  });

  it('is never negative', () => {
    expect(wholeYen('-5')).toBe(0);
  });
});

describe('blockedYenKey', () => {
  it('blocks the keys that make a decimal, a sign or an exponent', () => {
    for (const key of ['.', ',', '-', '+', 'e', 'E']) expect(blockedYenKey(key)).toBe(true);
  });

  it('lets digits and editing keys through', () => {
    for (const key of ['0', '5', 'Backspace', 'Tab', 'ArrowLeft']) expect(blockedYenKey(key)).toBe(false);
  });
});
