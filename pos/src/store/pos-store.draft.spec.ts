import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../lib/menu-api', () => ({ getRestaurantMenu: vi.fn(async () => []), getAggregatorMenu: vi.fn(async () => []) }));
vi.mock('../lib/customer-api', () => ({
  getCustomerGroups: vi.fn(async () => []),
  getCustomerTerritories: vi.fn(async () => []),
  getCustomerRecord: vi.fn(async () => null),
}));

const tableOrders: Record<string, unknown> = {};

vi.mock('../lib/order-api', async (importOriginal) => {
  const original = await importOriginal<typeof import('../lib/order-api')>();
  return {
    ...original,
    getTableOrder: vi.fn(async (table: string) => ({ message: tableOrders[table] ?? {} })),
  };
});

import { generateUniqueId, usePOSStore } from './pos-store';
import type { OrderItem } from './pos-store';

const BEER_ROWS = [{ item_code: 'ビール', item_name: 'ビール', qty: 2, rate: 500, amount: 1000, comment: '' }];

function line(id: string, quantity: number, extra: Record<string, unknown> = {}): OrderItem {
  const base = { id, item: id, name: id, item_name: id, price: 1000, quantity, comment: '', ...extra } as unknown as OrderItem;
  return { ...base, uniqueId: generateUniqueId(base) };
}

// What the cashier has typed in but not confirmed yet is a draft. Changing the order type or choosing a table must not
// throw it away silently (2026-11-15: a take-away draft vanished when 店内 was tapped and a table with an order was chosen).
describe('an order that is not confirmed yet', () => {
  beforeEach(() => {
    tableOrders['MD-03'] = { name: 'INV-1', customer: 'c', items: BEER_ROWS, modified: '2026-11-15 10:00:00' };
    delete tableOrders['MD-05'];
    usePOSStore.setState({
      selectedOrderType: 'Take Away',
      selectedTable: null,
      selectedRoom: null,
      tableOrder: null,
      isUpdatingOrder: false,
      orderId: null,
      activeOrders: [line('握り', 1)],
      posProfile: null,
      error: null,
    });
  });

  it('is kept when the order type changes between take away and dine in', () => {
    usePOSStore.getState().setSelectedOrderType('Dine In');
    expect(usePOSStore.getState().activeOrders.map((l) => l.id)).toEqual(['握り']);
    usePOSStore.getState().setSelectedOrderType('Take Away');
    expect(usePOSStore.getState().activeOrders.map((l) => l.id)).toEqual(['握り']);
  });

  it('is dropped when the order being edited changes type (an order that exists is not a draft)', () => {
    usePOSStore.setState({ isUpdatingOrder: true, orderId: 'INV-9', selectedOrderType: 'Dine In' });
    usePOSStore.getState().setSelectedOrderType('Take Away');
    expect(usePOSStore.getState().activeOrders).toEqual([]);
  });

  it('is dropped when going to or from aggregators (their menu has other prices)', () => {
    usePOSStore.getState().setSelectedOrderType('Aggregators');
    expect(usePOSStore.getState().activeOrders).toEqual([]);
  });

  it('stays in the cart when the table chosen has no order', async () => {
    usePOSStore.getState().setSelectedOrderType('Dine In');
    usePOSStore.getState().setSelectedTable('MD-05', 'Room', false, true);
    await vi.waitFor(() => expect(usePOSStore.getState().orderLoading).toBe(false));
    const state = usePOSStore.getState();
    expect(state.activeOrders.map((l) => l.id)).toEqual(['握り']);
    expect(state.pendingDraft).toBeNull();
    expect(state.isUpdatingOrder).toBe(false);
  });

  it('waits for the cashier when the table chosen has an order: the table shows its order, the draft is held', async () => {
    usePOSStore.getState().setSelectedOrderType('Dine In');
    usePOSStore.getState().setSelectedTable('MD-03', 'Room', false, true);
    await vi.waitFor(() => expect(usePOSStore.getState().pendingDraft).not.toBeNull());
    const state = usePOSStore.getState();
    expect(state.pendingDraft!.items.map((l) => l.id)).toEqual(['握り']);
    expect(state.activeOrders.map((l) => l.id)).toEqual(['ビール']);
    expect(state.isUpdatingOrder).toBe(true);
  });

  it('is added to the order of the table when the cashier says so, as lines not sent to the kitchen', async () => {
    usePOSStore.getState().setSelectedOrderType('Dine In');
    usePOSStore.getState().setSelectedTable('MD-03', 'Room', false, true);
    await vi.waitFor(() => expect(usePOSStore.getState().pendingDraft).not.toBeNull());
    usePOSStore.getState().addPendingDraftToTable();
    const state = usePOSStore.getState();
    expect(state.pendingDraft).toBeNull();
    expect(state.activeOrders.map((l) => [l.id, l.quantity, l.sentQuantity ?? 0])).toEqual([
      ['ビール', 2, 2],
      ['握り', 1, 0],
    ]);
    expect(state.orderId).toBe('INV-1');
    expect(state.isUpdatingOrder).toBe(true);
  });

  it('the same dish the table already has becomes one line: more quantity, the new part not sent', async () => {
    usePOSStore.setState({ activeOrders: [line('ビール', 1)] });
    usePOSStore.getState().setSelectedOrderType('Dine In');
    usePOSStore.getState().setSelectedTable('MD-03', 'Room', false, true);
    await vi.waitFor(() => expect(usePOSStore.getState().pendingDraft).not.toBeNull());
    usePOSStore.getState().addPendingDraftToTable();
    const lines = usePOSStore.getState().activeOrders;
    expect(lines.map((l) => [l.id, l.quantity, l.sentQuantity ?? 0])).toEqual([['ビール', 3, 2]]);
  });

  it('is back as it was when the cashier cancels: no table, the draft in the cart, the order type before', async () => {
    usePOSStore.getState().setSelectedOrderType('Dine In');
    usePOSStore.getState().setSelectedTable('MD-03', 'Room', false, true);
    await vi.waitFor(() => expect(usePOSStore.getState().pendingDraft).not.toBeNull());
    usePOSStore.getState().cancelPendingDraft();
    const state = usePOSStore.getState();
    expect(state.pendingDraft).toBeNull();
    expect(state.selectedTable).toBeNull();
    expect(state.tableOrder).toBeNull();
    expect(state.isUpdatingOrder).toBe(false);
    expect(state.orderId).toBeNull();
    expect(state.selectedOrderType).toBe('Take Away');
    expect(state.activeOrders.map((l) => [l.id, l.quantity])).toEqual([['握り', 1]]);
  });

  it('nothing is held when the cart was empty: the table just shows its order (as before)', async () => {
    usePOSStore.setState({ activeOrders: [] });
    usePOSStore.getState().setSelectedOrderType('Dine In');
    usePOSStore.getState().setSelectedTable('MD-03', 'Room', false, true);
    await vi.waitFor(() => expect(usePOSStore.getState().orderLoading).toBe(false));
    expect(usePOSStore.getState().pendingDraft).toBeNull();
    expect(usePOSStore.getState().activeOrders.map((l) => l.id)).toEqual(['ビール']);
  });

  it('a table picked from somewhere that does not ask (no carry flag) behaves as before', async () => {
    usePOSStore.getState().setSelectedOrderType('Dine In');
    usePOSStore.getState().setSelectedTable('MD-03', 'Room');
    await vi.waitFor(() => expect(usePOSStore.getState().orderLoading).toBe(false));
    expect(usePOSStore.getState().pendingDraft).toBeNull();
    expect(usePOSStore.getState().activeOrders.map((l) => l.id)).toEqual(['ビール']);
  });
});
