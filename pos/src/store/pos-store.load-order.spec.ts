import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../lib/menu-api', () => ({ getRestaurantMenu: vi.fn(async () => []), getAggregatorMenu: vi.fn(async () => []) }));
vi.mock('../lib/customer-api', () => ({
  getCustomerGroups: vi.fn(async () => []),
  getCustomerTerritories: vi.fn(async () => []),
  getCustomerRecord: vi.fn(async () => null),
}));

const rows = [
  { item_code: 'Burger', item_name: 'Burger', qty: 1, rate: 180, amount: 180, comment: '' },
  { item_code: 'Burger', item_name: 'Burger', qty: 2, rate: 180, amount: 360, comment: '' },
  { item_code: 'Burger', item_name: 'Burger', qty: 2, rate: 180, amount: 360, comment: '辛さ控えめ' },
];

vi.mock('../lib/order-api', async (importOriginal) => {
  const original = await importOriginal<typeof import('../lib/order-api')>();
  return {
    ...original,
    getTableOrder: vi.fn(async () => ({ message: { name: 'INV-1', customer: 'c', items: rows, modified: '2026-11-10 10:00:00' } })),
  };
});

import { usePOSStore } from './pos-store';

// The order of a table as the register and the captain's screen load it (`loadTableOrder`): the rows of the same dish that the
// guests' orders made are ONE line, so that changing or deleting a line is what it says (2026-11-10).
describe('loadTableOrder', () => {
  beforeEach(() => {
    usePOSStore.setState({ activeOrders: [], error: null });
  });

  it('the rows of the same dish and note are one line; another note is another line', async () => {
    await usePOSStore.getState().loadTableOrder('MD-03');
    const lines = usePOSStore.getState().activeOrders;
    expect(lines.map((l) => [l.quantity, l.sentQuantity, l.comment || ''])).toEqual([
      [3, 3, ''],
      [2, 2, '辛さ控えめ'],
    ]);
  });

  it('changing the quantity of one line changes that line only; deleting it deletes that line only', async () => {
    await usePOSStore.getState().loadTableOrder('MD-03');
    const [plain, spicy] = usePOSStore.getState().activeOrders;
    await usePOSStore.getState().updateQuantity(plain.uniqueId!, 5);
    expect(usePOSStore.getState().activeOrders.map((l) => l.quantity)).toEqual([5, 2]);
    await usePOSStore.getState().removeFromOrder(spicy.uniqueId!);
    expect(usePOSStore.getState().activeOrders.map((l) => l.quantity)).toEqual([5]);
  });
});
