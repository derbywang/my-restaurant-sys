import { describe, expect, it } from 'vitest';

import { minutesOpen, normalizeOpenTables, selfOrderAction } from './self-order-tables';

const NOW = new Date('2026-12-11T12:30:00').getTime();

describe('minutesOpen', () => {
  it('is the whole minutes since the table was opened', () => {
    expect(minutesOpen('2026-12-11 12:18:30', NOW)).toBe(11);
    expect(minutesOpen('2026-12-11 12:30:00', NOW)).toBe(0);
    expect(minutesOpen('2026-12-11 11:00:00', NOW)).toBe(90);
  });

  it('is never negative (a clock a little behind the server)', () => {
    expect(minutesOpen('2026-12-11 12:31:00', NOW)).toBe(0);
  });

  it('is 0 when there is no usable time', () => {
    expect(minutesOpen(null, NOW)).toBe(0);
    expect(minutesOpen('', NOW)).toBe(0);
    expect(minutesOpen('not a time', NOW)).toBe(0);
  });
});

describe('normalizeOpenTables', () => {
  it('reads the answer of the server', () => {
    const answer = {
      message: {
        enabled: true,
        store_open: true,
        tables: [{ table: 'T-01', opened_at: '2026-12-11 12:00:00', expires_at: '2026-12-11 16:00:00', opened_by: 'a@b.c' }],
      },
    };
    const result = normalizeOpenTables(answer);
    expect(result.enabled).toBe(true);
    expect(result.storeOpen).toBe(true);
    expect(result.tables.get('T-01')?.openedAt).toBe('2026-12-11 12:00:00');
  });

  it('offers nothing when the answer is not what it should be', () => {
    for (const answer of [null, undefined, 'x', {}, { message: null }, { message: { enabled: 'yes' } }]) {
      const result = normalizeOpenTables(answer);
      expect(result.enabled).toBe(false);
      expect(result.tables.size).toBe(0);
    }
  });

  it('reads the tables the button is not offered for', () => {
    const result = normalizeOpenTables({ message: { enabled: true, store_open: true, tables: [], blocked: ['MD-03', '', null, 5, 'MD-04'] } });
    expect([...result.blocked].sort()).toEqual(['MD-03', 'MD-04']);
  });

  it('has none blocked when the server says nothing about it', () => {
    expect(normalizeOpenTables({ message: { enabled: true, store_open: true, tables: [] } }).blocked.size).toBe(0);
  });

  it('skips rows without a table name', () => {
    const result = normalizeOpenTables({ message: { enabled: true, store_open: true, tables: [{ table: '' }, { opened_at: 'x' }, null] } });
    expect(result.tables.size).toBe(0);
  });
});

describe('selfOrderAction', () => {
  const open = { enabled: true, storeOpen: true, blocked: new Set<string>(), tables: new Map([['T-01', { openedAt: '2026-12-11 12:00:00', expiresAt: null, openedBy: null }]]) };
  const closed = { enabled: true, storeOpen: true, blocked: new Set<string>(), tables: new Map() };

  it('is stop for an open table and start for a closed one', () => {
    expect(selfOrderAction(open, 'T-01', { isTakeAway: false })).toBe('stop');
    expect(selfOrderAction(closed, 'T-01', { isTakeAway: false })).toBe('start');
  });

  it('offers nothing when the branch does not use self ordering', () => {
    expect(selfOrderAction({ ...closed, enabled: false }, 'T-01', { isTakeAway: false })).toBe('none');
    expect(selfOrderAction({ ...closed, enabled: false, blocked: new Set(['T-01']) }, 'T-01', { isTakeAway: false })).toBe('none');
  });

  it('says why there is no button for a table whose bill is printed (the server refuses to open it)', () => {
    const printed = { ...closed, blocked: new Set(['T-01']) };
    expect(selfOrderAction(printed, 'T-01', { isTakeAway: false })).toBe('blocked');
    expect(selfOrderAction(printed, 'T-02', { isTakeAway: false })).toBe('start');
  });

  it('offers nothing for a take away table', () => {
    expect(selfOrderAction(closed, 'T-01', { isTakeAway: true })).toBe('none');
  });

  it('does not start while the store is closed, but can always stop', () => {
    expect(selfOrderAction({ ...closed, storeOpen: false }, 'T-01', { isTakeAway: false })).toBe('start-disabled');
    expect(selfOrderAction({ ...open, storeOpen: false }, 'T-01', { isTakeAway: false })).toBe('stop');
  });
});
