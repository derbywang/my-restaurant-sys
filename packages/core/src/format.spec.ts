import { describe, expect, it } from 'vitest';
import { elapsedMinutes, formatInvoiceTime, parseServerDatetime } from './format';

// The server sends "2026-11-07 20:24:24.397245" (a space, microseconds). Safari does not parse that with
// `new Date(string)`, so the pieces are read by hand and built as a local date.
describe('parseServerDatetime', () => {
  it('reads the Frappe format with microseconds', () => {
    const d = parseServerDatetime('2026-11-07 20:24:24.397245');
    expect(d).toEqual(new Date(2026, 10, 7, 20, 24, 24));
  });

  it('reads it without fractions and with a T', () => {
    expect(parseServerDatetime('2026-11-07 20:24:24')).toEqual(new Date(2026, 10, 7, 20, 24, 24));
    expect(parseServerDatetime('2026-11-07T20:24:24')).toEqual(new Date(2026, 10, 7, 20, 24, 24));
    expect(parseServerDatetime('2026-11-07T20:24:24.5')).toEqual(new Date(2026, 10, 7, 20, 24, 24));
  });

  it('gives null for nothing, nonsense and a time of day without a date', () => {
    expect(parseServerDatetime(null)).toBeNull();
    expect(parseServerDatetime('')).toBeNull();
    expect(parseServerDatetime('later')).toBeNull();
    expect(parseServerDatetime('20:24:24.397245')).toBeNull();
    expect(parseServerDatetime('2026-13-45 99:99:99')).toBeNull();
  });
});

describe('elapsedMinutes', () => {
  it('counts across midnight (a bill from yesterday is not negative)', () => {
    const now = new Date(2026, 10, 8, 18, 7, 0).getTime();
    expect(elapsedMinutes('2026-11-07 20:24:24.397245', now)).toBe(1302);
    expect(elapsedMinutes('2026-11-06 20:24:24', now)).toBe(1302 + 1440);
  });

  it('is zero for a time that is a little in the future (clock difference)', () => {
    const now = new Date(2026, 10, 8, 18, 7, 0).getTime();
    expect(elapsedMinutes('2026-11-08 18:09:00', now)).toBe(0);
  });

  it('is null when there is nothing to count', () => {
    expect(elapsedMinutes(null)).toBeNull();
    expect(elapsedMinutes('20:24:24')).toBeNull();
  });
});

describe('formatInvoiceTime', () => {
  it('shows only the clock for today and the date as well for another day', () => {
    const today = new Date();
    const pad = (n: number) => String(n).padStart(2, '0');
    const stamp = (d: Date) =>
      `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} 20:24:24.397245`;
    const todayText = formatInvoiceTime(stamp(today));
    const older = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 3);
    const olderText = formatInvoiceTime(stamp(older));
    expect(todayText).not.toBe('Invalid Date');
    expect(olderText).not.toBe('Invalid Date');
    expect(olderText.length).toBeGreaterThan(todayText.length);
    expect(olderText).toContain(String(older.getDate()));
  });

  it('keeps answering for the old time-only value and for nothing', () => {
    expect(formatInvoiceTime('20:24:24.397245')).toBe('20:24');
    expect(formatInvoiceTime(null)).toBe('No bill activity yet');
  });
});
