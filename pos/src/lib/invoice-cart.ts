import type { POSInvoiceItem } from './order-api';
import type { OrderItem } from '../store/pos-store';

/**
 * The cart lines of a saved order, as every screen that opens an order shows them: with the note of the line (a line
 * sent to the kitchen keeps it, see lib/sent-items.ts) and the quantity that went to the kitchen.
 * `makeId` gives a line its id in the cart (the same rule as a line added from the menu).
 */
export function cartLinesFromInvoice(items: POSInvoiceItem[], makeId: (line: OrderItem) => string): OrderItem[] {
  return mergeCartLines((items || []).map((item) => {
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
  }));
}

/**
 * The rows of an order that have the same cart id (the same dish, variant, add-ons and note) become ONE cart line, in the order of
 * the first row: quantity, quantity sent to the kitchen and amount are added. The guests' orders (self ordering) add a new row
 * each time, so a dish ordered in three rounds is three rows; with the same id for all of them, changing the quantity of one
 * line changed all of them and deleting one deleted all. The server takes the cart as it is (it compares what the kitchen has
 * with what is asked by dish and note, not row by row), so the order is saved with one row for the line.
 */
export function mergeCartLines(lines: OrderItem[]): OrderItem[] {
  const merged = new Map<string, OrderItem>();
  for (const line of lines) {
    const key = line.uniqueId ?? '';
    const first = merged.get(key);
    if (!first) {
      merged.set(key, { ...line });
    } else {
      first.quantity = (first.quantity ?? 0) + (line.quantity ?? 0);
      first.sentQuantity = (first.sentQuantity ?? 0) + (line.sentQuantity ?? 0);
      const amounts = first as unknown as { amount?: number };
      amounts.amount = (amounts.amount ?? 0) + ((line as unknown as { amount?: number }).amount ?? 0);
    }
  }
  return [...merged.values()];
}
