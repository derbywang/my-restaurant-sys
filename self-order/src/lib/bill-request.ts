import type { CustomerOrder } from './api'

/**
 * Whether the page says 「お会計をお呼びしました」 (and not the button). True after the guest pressed the button here, and also
 * after a reload of the page: the order says when it has a call that the staff have not dealt with. Once the bill is
 * printed the staff have dealt with it, and the page shows the bill state instead.
 */
export function billAsked(order: CustomerOrder | null, pressedHere: boolean): boolean {
  if (!order || order.billed) return false
  return pressedHere || order.bill_requested === true
}
