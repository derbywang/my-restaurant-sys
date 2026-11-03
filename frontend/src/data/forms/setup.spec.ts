import { describe, expect, it } from 'vitest';
import { validateFieldValue } from '@ury/core';
import setup from './setup.json';
import validationMessages from '../validations.json';

const field = (id: string) => (setup.fields as { id: string; validations?: string[] }[]).find((f) => f.id === id)!;
const check = (id: string, value: string) => validateFieldValue(value, field(id).validations ?? [], validationMessages);

describe('the company name and abbreviation of the first step', () => {
  it('accepts a two-character name: 「中華」 is a normal name in Japanese, Chinese and Korean', () => {
    expect(check('company_name', '中華').valid).toBe(true);
    expect(check('company_name', '店').valid).toBe(true);
    expect(check('company_abbr', '中').valid).toBe(true);
  });

  it('still needs a value', () => {
    expect(check('company_name', '').valid).toBe(false);
    expect(check('company_abbr', '').valid).toBe(false);
  });

  it('keeps the abbreviation short', () => {
    expect(check('company_abbr', 'ABCDEF').valid).toBe(false);
  });
});
