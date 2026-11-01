/**
 * What the closing dialog shows per payment mode. Pure functions (no network, no React) so
 * they can be unit tested: `yarn workspace pos test`.
 *
 * The rule is the one of ERPNext's POS Closing Entry and of Sub POS Closing
 * (sub_pos_closing.js): Expected = opening amount + the payments of the shift, with the
 * change taken off. Closing is what the cashier counts in the drawer (opening amount
 * included), and Difference = Closing - Expected.
 */
import type {
  ClosingPaymentSummary,
  POSClosingInvoice,
  POSClosingPayment,
} from './pos-closing-api';

export interface OpeningBalanceDetail {
  mode_of_payment: string;
  opening_amount: number;
}

export interface AggregatedTotals {
  grandTotal: number;
  netTotal: number;
  totalQty: number;
}

/**
 * The payment row the change came out of, chosen like ERPNext's
 * get_change_payment_row: the Cash row of the change account, else any row of
 * that account, else any Cash row.
 */
export function changePaymentRow(
  payments: POSClosingPayment[],
  changeAccount: string
): POSClosingPayment | undefined {
  const sameAccount = payments.filter((p) => p.account === changeAccount);
  return (
    sameAccount.find((p) => p.type === 'Cash') ||
    sameAccount[0] ||
    payments.find((p) => p.type === 'Cash')
  );
}

/**
 * Aggregates raw POS Invoice dicts into closing totals and per-mode amounts of the shift,
 * faithfully porting the logic in ury/ury/doctype/sub_pos_closing/sub_pos_closing.js
 * (refresh_payments / set_form_data): sums grand_total/net_total/total_qty, and for each
 * invoice subtracts its change_amount from the payment row the change came out of (see
 * changePaymentRow) before accumulating by mode_of_payment. The opening amount is added
 * by buildRows.
 */
export function aggregateInvoices(invoices: POSClosingInvoice[]): {
  totals: AggregatedTotals;
  expectedByMode: Record<string, number>;
} {
  const totals: AggregatedTotals = { grandTotal: 0, netTotal: 0, totalQty: 0 };
  const expectedByMode: Record<string, number> = {};

  invoices.forEach((invoice) => {
    totals.grandTotal += Number(invoice.grand_total) || 0;
    totals.netTotal += Number(invoice.net_total) || 0;
    totals.totalQty += Number(invoice.total_qty) || 0;

    const payments = invoice.payments || [];
    const changeRow = changePaymentRow(payments, invoice.account_for_change_amount);
    payments.forEach((payment) => {
      let amount = Number(payment.amount) || 0;
      if (payment === changeRow) {
        amount -= Number(invoice.change_amount) || 0;
      }
      expectedByMode[payment.mode_of_payment] =
        (expectedByMode[payment.mode_of_payment] || 0) + amount;
    });
  });

  return { totals, expectedByMode };
}

/**
 * One row per payment mode that has an opening amount or a payment in the shift.
 * Expected = opening amount + payments of the shift (`shiftByMode`, change already taken off).
 */
export function buildRows(
  openingBalances: OpeningBalanceDetail[],
  shiftByMode: Record<string, number>
): ClosingPaymentSummary[] {
  const rows = new Map<string, ClosingPaymentSummary>();

  openingBalances.forEach((detail) => {
    const opening = Number(detail.opening_amount) || 0;
    rows.set(detail.mode_of_payment, {
      mode_of_payment: detail.mode_of_payment,
      opening_amount: opening,
      expected_amount: opening,
      closing_amount: 0,
      difference: 0,
    });
  });

  Object.entries(shiftByMode).forEach(([mode, amount]) => {
    const existing = rows.get(mode);
    if (existing) {
      existing.expected_amount += amount;
    } else {
      rows.set(mode, {
        mode_of_payment: mode,
        opening_amount: 0,
        expected_amount: amount,
        closing_amount: 0,
        difference: 0,
      });
    }
  });

  return Array.from(rows.values());
}
