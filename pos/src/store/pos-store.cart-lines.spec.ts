import { beforeEach, describe, expect, it } from 'vitest';

import { usePOSStore, type OrderItem } from './pos-store';

// How the register's cart makes lines (a statement of what is, found while testing the receipt on 2026-11-10): a line is one
// dish with one variant, one set of add-ons and ONE NOTE. The same dish added again with the same note adds to the line; with
// another note (typed in the dialog of the dish when it is added) it is a line of its own.
const burger = (quantity: number, comment?: string): OrderItem =>
  ({ id: 'Burger', name: 'Burger', item_name: 'Burger', price: 180, quantity, comment } as unknown as OrderItem);

describe('the lines of the cart', () => {
  beforeEach(() => {
    usePOSStore.setState({ activeOrders: [], error: null });
  });

  it('the same dish with the same note is one line, whatever the number of times it is added', async () => {
    const { addToOrder } = usePOSStore.getState();
    await addToOrder(burger(1));
    await addToOrder(burger(2));
    const lines = usePOSStore.getState().activeOrders;
    expect(lines).toHaveLength(1);
    expect(lines[0].quantity).toBe(3);
  });

  it('the same dish with another note is a line of its own', async () => {
    const { addToOrder } = usePOSStore.getState();
    await addToOrder(burger(3));
    await addToOrder(burger(3, '辛さ控えめ'));
    const lines = usePOSStore.getState().activeOrders;
    expect(lines).toHaveLength(2);
    expect(lines.map((l) => [l.quantity, l.comment || ''])).toEqual([[3, ''], [3, '辛さ控えめ']]);
  });

  it('the same note again adds to the line of that note', async () => {
    const { addToOrder } = usePOSStore.getState();
    await addToOrder(burger(3));
    await addToOrder(burger(3, '辛さ控えめ'));
    await addToOrder(burger(1, '辛さ控えめ'));
    const lines = usePOSStore.getState().activeOrders;
    expect(lines).toHaveLength(2);
    expect(lines[1].quantity).toBe(4);
  });

  it('changing the note of a line later changes that whole line (it does not split it)', async () => {
    const { addToOrder, updateItemComment } = usePOSStore.getState();
    await addToOrder(burger(3));
    const line = usePOSStore.getState().activeOrders[0];
    updateItemComment(line.uniqueId!, '辛さ控えめ');
    const lines = usePOSStore.getState().activeOrders;
    expect(lines).toHaveLength(1);
    expect(lines[0].comment).toBe('辛さ控えめ');
  });
});
