// Small rules of the order tabs.
import type { OrderType } from '../data/order-types';

/** The table to send with an order: only a dine in order has one. A take away, delivery, phone or
 * aggregator order that still remembers the table picked earlier must not send it (the server would
 * mark that table as in use). */
export function tableForSubmit(orderType: OrderType, selectedTable: string | null | undefined): string | undefined {
  return orderType === 'Dine In' && selectedTable ? selectedTable : undefined;
}

export type TabCloseAction = 'close' | 'remove_cart' | 'unsaved_changes';

/** What closing a tab needs: nothing, a confirmation to throw away a new cart, or a confirmation to
 * throw away the changes made to an order that is saved on the server. */
export function tabCloseAction(tab: {
  cartIsEmpty: boolean;
  isUpdatingOrder: boolean;
  cartHash: string;
  originalCartHash: string;
}): TabCloseAction {
  if (tab.cartIsEmpty) return 'close';
  if (!tab.isUpdatingOrder) return 'remove_cart';
  return tab.cartHash !== tab.originalCartHash ? 'unsaved_changes' : 'close';
}
