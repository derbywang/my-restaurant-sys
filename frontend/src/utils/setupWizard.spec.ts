import { describe, expect, it } from 'vitest';
import {
  fiscalYearEnd,
  fiscalYearLabel,
  fiscalYearStart,
  formatIsoDate,
  formatJapaneseDate,
  missingPriceMessage,
  missingPriceNames,
  parsePriceInput,
  paymentHint,
  priceColumnLabel,
  priceInputValue,
} from './setupWizard';

describe('fiscalYearStart', () => {
  it('is January 1st for Japan, in year-month-day form', () => {
    expect(fiscalYearStart('Japan', 2026)).toBe('2026-01-01');
  });

  it('follows the country table for the others', () => {
    expect(fiscalYearStart('India', 2026)).toBe('2026-04-01');
    expect(fiscalYearStart('Australia', 2026)).toBe('2026-07-01');
    expect(fiscalYearStart('Nepal', 2026)).toBe('2026-07-16');
  });

  it('is January 1st for a country that is not in the table', () => {
    expect(fiscalYearStart('Germany', 2026)).toBe('2026-01-01');
  });

  it('is always a valid year-month-day string', () => {
    for (const country of ['Japan', 'India', 'Iran', 'Afghanistan', 'Germany']) {
      expect(fiscalYearStart(country, 2026)).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    }
  });
});

describe('fiscalYearEnd', () => {
  it('is one year later, minus a day', () => {
    expect(fiscalYearEnd('2026-01-01')).toBe('2026-12-31');
    expect(fiscalYearEnd('2026-04-01')).toBe('2027-03-31');
    expect(fiscalYearEnd('2026-07-16')).toBe('2027-07-15');
  });

  it('handles a leap day', () => {
    expect(fiscalYearEnd('2027-03-01')).toBe('2028-02-29');
  });
});

describe('date display', () => {
  it('shows the ISO form without ambiguity', () => {
    expect(formatIsoDate('2026-04-01')).toBe('2026-04-01');
    expect(formatIsoDate('2026-4-1')).toBe('2026-04-01');
    expect(formatIsoDate('')).toBe('');
  });

  it('shows the Japanese form', () => {
    expect(formatJapaneseDate('2026-04-01')).toBe('2026年4月1日');
    expect(formatJapaneseDate('2026-01-04')).toBe('2026年1月4日');
    expect(formatJapaneseDate('')).toBe('');
  });

  it('shows the whole fiscal year, so April 1st cannot be read as January 4th', () => {
    expect(fiscalYearLabel('2026-04-01')).toBe('2026年4月1日 〜 2027年3月31日');
    expect(fiscalYearLabel('2026-01-04')).toBe('2026年1月4日 〜 2027年1月3日');
    expect(fiscalYearLabel('')).toBe('');
  });
});

describe('priceColumnLabel', () => {
  it('names the currency of the company', () => {
    expect(priceColumnLabel('JPY')).toBe('Price (JPY)');
  });

  it('is plain Price without a currency', () => {
    expect(priceColumnLabel(null)).toBe('Price');
    expect(priceColumnLabel(undefined)).toBe('Price');
  });
});

describe('paymentHint', () => {
  it('names the Japanese methods for Japan', () => {
    expect(paymentHint(true)).toContain('credit cards');
    expect(paymentHint(true)).toContain('PayPay');
  });

  it('names no country-specific method elsewhere', () => {
    expect(paymentHint(false)).not.toMatch(/UPI|PayPay|クレジット/);
    expect(paymentHint(false)).toContain('Cash');
  });

  it('is written in one language: the wizard text is English, no Japanese in it', () => {
    expect(paymentHint(true)).not.toMatch(/[\u3000-\u30ff\u4e00-\u9fff]/);
    expect(paymentHint(false)).not.toMatch(/[\u3000-\u30ff\u4e00-\u9fff]/);
  });
});

describe('parsePriceInput', () => {
  it('an empty box is no price yet, not 0', () => {
    expect(parsePriceInput('')).toBeNull();
    expect(parsePriceInput('  ')).toBeNull();
  });

  it('reads a number, 0 included', () => {
    expect(parsePriceInput('0')).toBe(0);
    expect(parsePriceInput('250')).toBe(250);
    expect(parsePriceInput('12.5')).toBe(12.5);
  });

  it('something that is not a price is no price', () => {
    expect(parsePriceInput('abc')).toBeNull();
    expect(parsePriceInput('-3')).toBeNull();
  });
});

describe('priceInputValue', () => {
  it('shows nothing for no price, so the box can be cleared', () => {
    expect(priceInputValue(null)).toBe('');
    expect(priceInputValue(undefined)).toBe('');
    expect(priceInputValue(0)).toBe('0');
    expect(priceInputValue(250)).toBe('250');
  });
});

describe('missingPriceNames', () => {
  it('lists the named items that have no price; a price of 0 is a price', () => {
    const items = [
      { name: 'ラーメン', price: null },
      { name: 'ビール', price: 0 },
      { name: '', price: null },
      { name: '餃子', price: 480 },
      { name: 'お茶', price: null },
    ];
    expect(missingPriceNames(items)).toEqual(['ラーメン', 'お茶']);
  });

  it('is empty when every named item has a price', () => {
    expect(missingPriceNames([{ name: 'a', price: 1 }])).toEqual([]);
    expect(missingPriceNames([])).toEqual([]);
  });

  it('has a message naming them', () => {
    expect(missingPriceMessage(['ラーメン', 'お茶'])).toContain('ラーメン, お茶');
  });
});
