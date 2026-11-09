import { describe, expect, it } from 'vitest';
import { cartLinesFromInvoice, mergeCartLines } from './invoice-cart';
import { generateUniqueId } from '../store/pos-store';
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

// The guests' orders (self ordering) add a new row of the order every time: the same dish arrives as several rows. The cart of
// the register has one line for a dish with its variant, add-ons and note (its id), so rows with the same id must be ONE line,
// or changing the quantity of one of them changes all of them and deleting one deletes all (found 2026-11-10).
describe('rows of the same dish become one cart line', () => {
  const burgers = [
    row({ item_code: 'Burger', item_name: 'Burger', qty: 1, rate: 180, amount: 180 }),
    row({ item_code: 'Burger', item_name: 'Burger', qty: 2, rate: 180, amount: 360 }),
  ];

  it('the quantity, the quantity sent to the kitchen and the amount are added', () => {
    const lines = cartLinesFromInvoice(burgers, generateUniqueId);
    expect(lines).toHaveLength(1);
    expect(lines[0]).toMatchObject({ quantity: 3, sentQuantity: 3, amount: 540 });
  });

  it('a different note is another line, and the order of first appearance is kept', () => {
    const lines = cartLinesFromInvoice(
      [
        row({ item_code: 'Burger', item_name: 'Burger', qty: 3, amount: 540 }),
        row({ item_code: 'Sake', item_name: 'Sake', qty: 1, amount: 500 }),
        row({ item_code: 'Burger', item_name: 'Burger', qty: 2, amount: 360, comment: '辛さ控えめ' }),
        row({ item_code: 'Burger', item_name: 'Burger', qty: 1, amount: 180 }),
      ],
      generateUniqueId
    );
    expect(lines.map((l) => [l.id, l.quantity, l.comment])).toEqual([
      ['Burger', 4, ''],
      ['Sake', 1, ''],
      ['Burger', 2, '辛さ控えめ'],
    ]);
  });

  it('every line has an id of its own (so a change of one line is a change of that line)', () => {
    const lines = cartLinesFromInvoice(burgers, generateUniqueId);
    expect(new Set(lines.map((l) => l.uniqueId)).size).toBe(lines.length);
  });

  it('mergeCartLines leaves lines with different ids alone', () => {
    const lines = [
      { uniqueId: 'a', quantity: 1, sentQuantity: 1, amount: 10 },
      { uniqueId: 'b', quantity: 2, sentQuantity: 2, amount: 20 },
    ] as never[];
    expect(mergeCartLines(lines)).toHaveLength(2);
  });
});
