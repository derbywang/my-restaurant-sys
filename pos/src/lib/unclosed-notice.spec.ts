import { describe, expect, it } from 'vitest';
import { acknowledgementMissing } from './unclosed-notice';

const waiting = { count: 7, total: 4125, oldest_date: '2026-11-02' };

describe('acknowledgementMissing (the opening screen asks to confirm invoices that were never closed)', () => {
  it('blocks the opening while invoices wait and the cashier has not confirmed', () => {
    expect(acknowledgementMissing(waiting, false)).toBe(true);
  });

  it('lets the cashier open after the confirmation', () => {
    expect(acknowledgementMissing(waiting, true)).toBe(false);
  });

  it('asks for nothing when there are no such invoices', () => {
    expect(acknowledgementMissing(null, false)).toBe(false);
    expect(acknowledgementMissing(undefined, false)).toBe(false);
    expect(acknowledgementMissing({ count: 0, total: 0, oldest_date: '' }, false)).toBe(false);
  });
});
