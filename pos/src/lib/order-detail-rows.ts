// The rows of the order detail of the order list (「伝票」→「注文明細」), joined the way the edit screen (the cart, see
// lib/invoice-cart.ts) and the receipt join them: the rows of the same dish and the same note are ONE row (quantity and amount
// added); another note is another row; the order of the first appearance is kept. The guests' orders (self ordering) add a new
// row of the order every time, so before this the detail showed the dish once for each round.
export interface DetailRow {
  name?: string;
  item_code?: string | null;
  item_name: string;
  qty: number;
  rate?: number;
  amount: number;
  comment?: string | null;
}

export function mergeDetailRows<T extends DetailRow>(rows: T[]): T[] {
  const merged = new Map<string, T>();
  for (const row of rows) {
    const note = (row.comment ?? '').trim();
    const key = `${row.item_code || row.item_name}\u0000${note}`;
    const first = merged.get(key);
    if (!first) {
      merged.set(key, { ...row, comment: note });
    } else {
      first.qty += row.qty;
      first.amount += row.amount;
    }
  }
  return [...merged.values()];
}
