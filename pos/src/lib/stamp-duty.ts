/**
 * 収入印紙: cash received of 50,000 yen or more (counted without the consumption tax) needs a stamp on a paper receipt
 * (the 税理士, 2026-11-09). The cashier is told before the payment is confirmed. The same rule as `stamp_duty_needed`
 * in ury/ury/api/receipt.py, which puts the place for the stamp on the receipt; both have the same test cases.
 */
import type { PaymentRow } from './payment-change';

export const STAMP_THRESHOLD = 50000;

export interface StampNotice {
  needed: boolean;
  /** The cash that stays with the shop: what was handed over, minus the change. */
  cashPaid: number;
  /** That cash without the tax. */
  netCash: number;
}

const NONE: StampNotice = { needed: false, cashPaid: 0, netCash: 0 };

export function stampNotice(
  payments: PaymentRow[],
  types: Record<string, string>,
  due: number,
  netTotal: number
): StampNotice {
  if (Object.keys(types).length === 0 || due <= 0 || netTotal <= 0) return NONE;
  const cashEntered = payments.filter((p) => types[p.mode_of_payment] === 'Cash').reduce((sum, p) => sum + p.amount, 0);
  const otherEntered = payments.filter((p) => types[p.mode_of_payment] !== 'Cash').reduce((sum, p) => sum + p.amount, 0);
  const cashPaid = Math.min(cashEntered, Math.max(0, due - otherEntered));
  if (cashPaid <= 0) return NONE;
  const netCash = Math.floor((cashPaid * netTotal) / due);
  return { needed: netCash >= STAMP_THRESHOLD, cashPaid, netCash };
}
