import { describe, expect, it } from 'vitest';
import { cartLinesFromInvoice } from './invoice-cart';
import type { POSInvoiceItem } from './order-api';

const row = (over: Partial<POSInvoiceItem>): POSInvoiceItem =>
  ({ item_code: 'SAKE', item_name: 'Sake', qty: 2, rate: 500, amount: 1000, comment: '', ...over }) as POSInvoiceItem;

describe('cartLinesFromInvoice', () => {
  it('keeps the note of a line and the quantity that went to the kitchen', () => {
    const [line] = cartLinesFromInvoice([row({ comment: '冷えたもの' })], () => 'id');
    expect(line.comment).toBe('冷えたもの');
    expect(line.sentQuantity).toBe(2);
    expect(line.quantity).toBe(2);
  });

  it('gives a line without a note an empty one and the id of the rule', () => {
    const [line] = cartLinesFromInvoice([row({ comment: undefined as never })], (l) => `${l.id}-${l.comment}`);
    expect(line.comment).toBe('');
    expect(line.uniqueId).toBe('SAKE-');
  });
});
