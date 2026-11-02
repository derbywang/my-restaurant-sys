import { describe, expect, it } from 'vitest';
import { isRegistrationNumber } from './registrationNumber';

describe('isRegistrationNumber', () => {
  it('accepts T and 13 digits, ignoring surrounding spaces', () => {
    expect(isRegistrationNumber('T1234567890123')).toBe(true);
    expect(isRegistrationNumber(' T1234567890123 ')).toBe(true);
  });

  it('rejects everything else', () => {
    for (const value of ['', '1234567890123', 'T123456789012', 'T12345678901234', 't1234567890123', 'T12345678901AB', 'T-123456789012', null, undefined]) {
      expect(isRegistrationNumber(value)).toBe(false);
    }
  });
});
