import { describe, expect, it } from 'vitest';
import { aggregateInvoices, buildRows, changePaymentRow } from './closing-rows';
import type { POSClosingInvoice, POSClosingPayment } from './pos-closing-api';

const cash = (amount: number, account = 'Cash - A'): POSClosingPayment => ({
  mode_of_payment: 'Cash',
  amount,
  account,
  type: 'Cash',
});
const card = (amount: number): POSClosingPayment => ({
  mode_of_payment: 'Card',
  amount,
  account: 'Bank - A',
  type: 'Bank',
});
const invoice = (
  payments: POSClosingPayment[],
  change = 0,
  changeAccount = 'Cash - A',
  grand = 0
): POSClosingInvoice => ({
  name: 'INV',
  grand_total: grand,
  net_total: grand,
  total_qty: 1,
  change_amount: change,
  account_for_change_amount: changeAccount,
  taxes: [],
  payments,
});

describe('buildRows', () => {
  it('adds the opening amount to the payments of the shift', () => {
    const rows = buildRows([{ mode_of_payment: 'Cash', opening_amount: 2000 }], { Cash: 15658 });
    expect(rows).toEqual([
      {
        mode_of_payment: 'Cash',
        opening_amount: 2000,
        expected_amount: 17658,
        closing_amount: 0,
        difference: 0,
      },
    ]);
  });

  it('expects just the opening amount when nothing was paid in the mode', () => {
    const [row] = buildRows([{ mode_of_payment: 'Cash', opening_amount: 2000 }], {});
    expect(row.expected_amount).toBe(2000);
  });

  it('makes a row for a mode that has payments but no opening amount', () => {
    const rows = buildRows([{ mode_of_payment: 'Cash', opening_amount: 2000 }], { Card: 3000 });
    const byMode = Object.fromEntries(rows.map((r) => [r.mode_of_payment, r]));
    expect(byMode.Card).toMatchObject({ opening_amount: 0, expected_amount: 3000 });
    expect(byMode.Cash).toMatchObject({ opening_amount: 2000, expected_amount: 2000 });
  });
});

describe('aggregateInvoices', () => {
  it('takes the change off the cash', () => {
    const { expectedByMode } = aggregateInvoices([invoice([cash(1000)], 730)]);
    expect(expectedByMode.Cash).toBe(270);
  });

  it('takes the change off the cash row when the change account matches no payment', () => {
    const { expectedByMode } = aggregateInvoices([invoice([cash(1000)], 730, 'Other')]);
    expect(expectedByMode.Cash).toBe(270);
  });

  it('adds up the invoices and the totals', () => {
    const { totals, expectedByMode } = aggregateInvoices([
      invoice([cash(1100)], 0, 'Cash - A', 1100),
      invoice([card(550)], 0, 'Cash - A', 550),
    ]);
    expect(expectedByMode).toEqual({ Cash: 1100, Card: 550 });
    expect(totals).toEqual({ grandTotal: 1650, netTotal: 1650, totalQty: 2 });
  });

  it('the drawer: opening 2,000 + 15,658 in cash expects 17,658', () => {
    const { expectedByMode } = aggregateInvoices([invoice([cash(16388)], 730)]);
    const [row] = buildRows([{ mode_of_payment: 'Cash', opening_amount: 2000 }], expectedByMode);
    expect(row.expected_amount).toBe(2000 + 16388 - 730);
  });
});

describe('changePaymentRow', () => {
  it('prefers the Cash row of the change account, then any row of it, then any Cash row', () => {
    const a = cash(1, 'Cash - A');
    const b = cash(2, 'Cash - B');
    const bank = card(3);
    expect(changePaymentRow([b, a], 'Cash - A')).toBe(a);
    expect(changePaymentRow([bank, b], 'Bank - A')).toBe(bank);
    expect(changePaymentRow([bank, b], 'Nothing')).toBe(b);
    expect(changePaymentRow([bank], 'Nothing')).toBeUndefined();
  });
});
