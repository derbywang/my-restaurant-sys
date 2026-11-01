/**
 * The amounts of an open order as the server calculates them.
 *
 * Backend: ury/ury/api/order_totals.py (preview_order_totals). The tax of each rate is
 * rounded on the server (ury/overrides/pos_invoice.py), so the POS shows these numbers
 * and never calculates tax or rounding itself.
 */

import { call } from '@ury/core';

export interface OrderTotalsTax {
  account_head: string;
  description?: string;
  /** Tax rate in percent. */
  rate: number;
  /** The amount (without tax) this rate is calculated on. */
  taxable_amount: number;
  tax_amount: number;
}

export interface OrderTotals {
  currency: string;
  /** Sum of the items, without tax, before the discount. */
  total: number;
  discount_percentage: number;
  discount_amount: number;
  /** After the discount, without tax. */
  net_total: number;
  taxes: OrderTotalsTax[];
  total_taxes_and_charges: number;
  grand_total: number;
  rounded_total: number;
  /** The tables of the bill (both bills of a merged bill), e.g. "T-01 + T-02". */
  table_label?: string;
}

/**
 * @param discountPercentage replaces the order's own discount when given
 *   (a percentage, 0-100); nothing is saved.
 */
export async function previewOrderTotals(
  invoice: string,
  discountPercentage?: number | null
): Promise<OrderTotals> {
  const response = await call.post<{ message: OrderTotals }>(
    'ury.ury.api.order_totals.preview_order_totals',
    {
      invoice,
      discount_percentage: discountPercentage ?? null,
    }
  );
  return response.message;
}

export interface CartTotalsRequest {
  /** The cart as sync_order takes it. */
  items: Array<{ item: string; item_name: string; qty: number }>;
  pos_profile: string;
  order_type: string;
  customer?: string;
  table?: string;
  /** The open order the cart will replace the lines of, if any. */
  invoice?: string | null;
}

/**
 * The amounts of a cart that has not been sent yet, as the server will have them once
 * sync_order saves it (preview_cart_totals; nothing is saved).
 */
export async function previewCartTotals(request: CartTotalsRequest): Promise<OrderTotals> {
  const response = await call.post<{ message: OrderTotals }>(
    'ury.ury.api.order_totals.preview_cart_totals',
    { ...request, items: JSON.stringify(request.items) }
  );
  return response.message;
}

/**
 * make_invoice refused to settle because the bill is not what the terminal showed (another
 * terminal added a dish, merged or unmerged it ...). The POS reads the amount due again.
 */
export function isAmountChangedError(err: unknown): boolean {
  const e = err as { exc_type?: string; exception?: string; httpStatus?: number } | null;
  return !!e && (e.exc_type === 'AmountChanged' || String(e.exception ?? '').includes('AmountChanged') || e.httpStatus === 409);
}
