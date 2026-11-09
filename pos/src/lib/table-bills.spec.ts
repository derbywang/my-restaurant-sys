import { describe, expect, it } from 'vitest';

import { groupTableBills, waitingBillsLabel, type BillRow } from './table-bills';

const row = (over: Partial<BillRow> = {}): BillRow => ({
  name: 'INV-1',
  restaurant_table: 'T-01',
  custom_merged_tables: null,
  waiter: 'a@x',
  grand_total: 1000,
  invoice_printed: 0,
  creation: '2026-11-10 10:00:00',
  ...over,
});

describe('groupTableBills', () => {
  it('a table with an order that is not printed: that order is the state of the table, nothing waits', () => {
    const bills = groupTableBills([row()]).get('T-01');
    expect(bills?.current).toMatchObject({ invoiceName: 'INV-1', waiter: 'a@x', grandTotal: 1000 });
    expect(bills?.waiting).toBeNull();
  });

  it('a table with only a printed bill: no current order, one bill waiting for the payment', () => {
    const bills = groupTableBills([row({ invoice_printed: 1, grand_total: 1655 })]).get('T-01');
    expect(bills?.current).toBeUndefined();
    expect(bills?.waiting).toEqual({ count: 1, total: 1655 });
  });

  it('the order that is not printed decides the state, whatever the order of the rows (the next guests are there)', () => {
    const printed = row({ name: 'INV-1', invoice_printed: 1, grand_total: 1655, creation: '2026-11-10 10:00:00' });
    const next = row({ name: 'INV-2', invoice_printed: 0, grand_total: 3000, waiter: 'b@x', creation: '2026-11-10 10:30:00' });
    for (const rows of [[printed, next], [next, printed]]) {
      const bills = groupTableBills(rows).get('T-01');
      expect(bills?.current).toMatchObject({ invoiceName: 'INV-2', waiter: 'b@x', grandTotal: 3000 });
      expect(bills?.waiting).toEqual({ count: 1, total: 1655 });
    }
  });

  it('several printed bills: the count and the sum', () => {
    const bills = groupTableBills([
      row({ name: 'INV-1', invoice_printed: 1, grand_total: 1655 }),
      row({ name: 'INV-2', invoice_printed: 1, grand_total: 1000 }),
    ]).get('T-01');
    expect(bills?.waiting).toEqual({ count: 2, total: 2655 });
  });

  it('with several orders that are not printed the oldest one is the current', () => {
    const rows = [
      row({ name: 'INV-2', creation: '2026-11-10 11:00:00' }),
      row({ name: 'INV-1', creation: '2026-11-10 10:00:00' }),
    ];
    expect(groupTableBills(rows).get('T-01')?.current?.invoiceName).toBe('INV-1');
  });

  it('the tables put together with the table of a bill have it too', () => {
    const bills = groupTableBills([row({ invoice_printed: 1, custom_merged_tables: 'T-02, T-03', grand_total: 500 })]);
    expect(bills.get('T-02')?.waiting).toEqual({ count: 1, total: 500 });
    expect(bills.get('T-03')?.waiting).toEqual({ count: 1, total: 500 });
  });

  it('a bill without a table (take away) is not on any table', () => {
    expect(groupTableBills([row({ restaurant_table: null })]).size).toBe(0);
  });
});

describe('waitingBillsLabel', () => {
  const yen = (n: number) => `¥${n.toLocaleString('en-US')}`;
  const t = (key: string, params?: Record<string, unknown>) => `${key}:${JSON.stringify(params)}`;

  it('one bill: the word and the amount', () => {
    expect(waitingBillsLabel({ count: 1, total: 1655 }, yen, t)).toBe('tables.bill_waiting:{"amount":"¥1,655"}');
  });

  it('several bills: the count and the sum', () => {
    expect(waitingBillsLabel({ count: 2, total: 2655 }, yen, t)).toBe('tables.bills_waiting:{"count":2,"amount":"¥2,655"}');
  });
});
