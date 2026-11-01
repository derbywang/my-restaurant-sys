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
