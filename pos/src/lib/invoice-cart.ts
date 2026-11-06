import type { POSInvoiceItem } from './order-api';
import type { OrderItem } from '../store/pos-store';

/**
 * The cart lines of a saved order, as every screen that opens an order shows them: with the note of the line (a line
 * sent to the kitchen keeps it, see lib/sent-items.ts) and the quantity that went to the kitchen.
 * `makeId` gives a line its id in the cart (the same rule as a line added from the menu).
 */
export function cartLinesFromInvoice(items: POSInvoiceItem[], makeId: (line: OrderItem) => string): OrderItem[] {
  return (items || []).map((item) => {
    const line = {
      id: item.item_code,
      name: item.item_name,
      price: item.rate,
      quantity: item.qty,
      amount: item.amount,
      image: item.image || null,
      item: item.item_code,
      item_name: item.item_name,
      item_image: null,
      course: '',
      description: item.description || '',
      special_dish: 0 as 0 | 1,
      tax_rate: 0,
      comment: item.comment || '',
      sentQuantity: item.qty,
    } as unknown as OrderItem;
    return { ...line, uniqueId: makeId(line) };
  });
}
