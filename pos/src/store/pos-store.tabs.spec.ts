import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../lib/menu-api', () => ({ getRestaurantMenu: vi.fn(async () => []), getAggregatorMenu: vi.fn(async () => []) }));
vi.mock('../lib/customer-api', () => ({
  getCustomerGroups: vi.fn(async () => []),
  getCustomerTerritories: vi.fn(async () => []),
  getCustomerRecord: vi.fn(async () => null),
}));

const KEY = 'posOrderTabsData';

function fakeStorage(initial: Record<string, string> = {}) {
  const data = { ...initial };
  return {
    data,
    getItem: (key: string) => (key in data ? data[key] : null),
    setItem: (key: string, value: string) => {
      data[key] = String(value);
    },
    removeItem: (key: string) => {
      delete data[key];
    },
  };
}

const PIZZA = { id: 'Pizza', name: 'Pizza', price: 250, quantity: 1, uniqueId: 'row-1' };
const SAKE = { id: 'Sake', name: 'Sake', price: 500, quantity: 1, uniqueId: 'row-2' };

/** What the POS saved just before the page was reloaded while an existing order was being edited. */
function savedWhileEditing(overrides: Record<string, unknown> = {}) {
  return JSON.stringify({
    tabOrder: [{ id: 'tab-1', name: 'Tab 1' }],
    activeTabId: 'tab-1',
    nextTabNumber: 2,
    heldTabs: {},
    activeTabState: {
      activeOrders: [PIZZA, SAKE],
      selectedCustomer: { id: '一般のお客様', name: '一般のお客様', phone: '' },
      selectedOrderType: 'Take Away',
      selectedTable: null,
      selectedRoom: null,
      selectedAggregator: null,
      orderId: 'INV-00051',
      isUpdatingOrder: true,
      orderComment: '少なめ',
      originalCartHash: 'hash',
      lastModifiedTime: '2026-11-03 10:05:25.424133',
      noOfPax: 3,
      ...overrides,
    },
  });
}

async function loadStore(saved?: string) {
  vi.resetModules();
  const storage = fakeStorage(saved ? { [KEY]: saved } : {});
  vi.stubGlobal('localStorage', storage);
  vi.stubGlobal('sessionStorage', fakeStorage());
  const { usePOSStore } = await import('./pos-store');
  return { usePOSStore, storage };
}

describe('reloading the page while an existing order is being edited', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('keeps editing that order: the button stays Update Order, not Add New Order', async () => {
    const { usePOSStore } = await loadStore(savedWhileEditing());
    const state = usePOSStore.getState();
    expect(state.isUpdatingOrder).toBe(true);
    expect(state.orderId).toBe('INV-00051');
  });

  it('keeps the time the order was last modified, so the server can check the edit', async () => {
    const { usePOSStore } = await loadStore(savedWhileEditing());
    expect(usePOSStore.getState().lastModifiedTime).toBe('2026-11-03 10:05:25.424133');
  });

  it('keeps the cart, the note and the number of guests', async () => {
    const { usePOSStore } = await loadStore(savedWhileEditing());
    const state = usePOSStore.getState();
    expect(state.activeOrders.map((item) => item.id)).toEqual(['Pizza', 'Sake']);
    expect(state.orderComment).toBe('少なめ');
    expect(state.noOfPax).toBe(3);
  });

  it('a page saved by an older version (no modified time, no guests) still opens as an edit', async () => {
    const { usePOSStore } = await loadStore(savedWhileEditing({ lastModifiedTime: undefined, noOfPax: undefined }));
    const state = usePOSStore.getState();
    expect(state.isUpdatingOrder).toBe(true);
    expect(state.lastModifiedTime).toBeNull();
    expect(state.noOfPax).toBe(1);
  });

  it('starts a new order when nothing was being edited', async () => {
    const { usePOSStore } = await loadStore(savedWhileEditing({ orderId: null, isUpdatingOrder: false, lastModifiedTime: null }));
    const state = usePOSStore.getState();
    expect(state.isUpdatingOrder).toBe(false);
    expect(state.orderId).toBeNull();
  });

  it('starts clean when nothing was saved', async () => {
    const { usePOSStore } = await loadStore();
    const state = usePOSStore.getState();
    expect(state.isUpdatingOrder).toBe(false);
    expect(state.orderId).toBeNull();
    expect(state.lastModifiedTime).toBeNull();
    expect(state.noOfPax).toBe(1);
    expect(state.activeOrders).toEqual([]);
  });
});

describe('opening a draft order from the order list', () => {
  const draft = (overrides = {}) => ({
    orderId: 'INV-00060',
    orderType: 'Take Away' as const,
    customer: null,
    table: null,
    room: null,
    items: [PIZZA as never],
    modified: '2026-11-03 11:00:00.123456',
    ...overrides,
  });

  it('takes the modified time of the order along', async () => {
    const { usePOSStore } = await loadStore();
    usePOSStore.getState().openDraftOrderInNewTab(draft());
    const state = usePOSStore.getState();
    expect(state.orderId).toBe('INV-00060');
    expect(state.isUpdatingOrder).toBe(true);
    expect(state.lastModifiedTime).toBe('2026-11-03 11:00:00.123456');
  });

  it('knows that every line of it was already sent to the kitchen (so a waiter cannot take a dish back there)', async () => {
    const { usePOSStore } = await loadStore();
    usePOSStore.getState().openDraftOrderInNewTab(draft({ items: [{ ...PIZZA, quantity: 2 }, SAKE] as never[] }));
    expect(usePOSStore.getState().activeOrders.map((item) => item.sentQuantity)).toEqual([2, 1]);
  });

  it('does not overwrite what a line already says it had sent', async () => {
    const { usePOSStore } = await loadStore();
    usePOSStore.getState().openDraftOrderInNewTab(draft({ items: [{ ...PIZZA, quantity: 3, sentQuantity: 2 }] as never[] }));
    expect(usePOSStore.getState().activeOrders[0].sentQuantity).toBe(2);
  });

  it('keeps each tab\'s own modified time when switching tabs', async () => {
    const { usePOSStore } = await loadStore();
    const store = usePOSStore.getState();
    const firstTab = store.activeTabId;
    store.openDraftOrderInNewTab(draft());
    const secondTab = usePOSStore.getState().activeTabId;
    usePOSStore.getState().switchTab(firstTab);
    expect(usePOSStore.getState().lastModifiedTime).toBeNull();
    usePOSStore.getState().switchTab(secondTab);
    expect(usePOSStore.getState().lastModifiedTime).toBe('2026-11-03 11:00:00.123456');
    expect(usePOSStore.getState().orderId).toBe('INV-00060');
  });

  it('saves it, so a reload keeps it', async () => {
    const { usePOSStore, storage } = await loadStore();
    usePOSStore.setState({ isInitializing: false });
    usePOSStore.getState().openDraftOrderInNewTab(draft());
    const saved = JSON.parse(storage.data[KEY]);
    expect(saved.activeTabState.lastModifiedTime).toBe('2026-11-03 11:00:00.123456');
    expect(saved.activeTabState.isUpdatingOrder).toBe(true);

    const reloaded = await loadStore(storage.data[KEY]);
    expect(reloaded.usePOSStore.getState().isUpdatingOrder).toBe(true);
    expect(reloaded.usePOSStore.getState().lastModifiedTime).toBe('2026-11-03 11:00:00.123456');
  });
});

describe('the table of a take away order', () => {
  const dineIn = (overrides: Record<string, unknown> = {}) =>
    savedWhileEditing({
      selectedOrderType: 'Dine In',
      selectedTable: 'MD-03',
      selectedRoom: 'Main Dining',
      orderId: null,
      isUpdatingOrder: false,
      lastModifiedTime: null,
      ...overrides,
    });

  it('is dropped when the order type changes from dine in to take away', async () => {
    const { usePOSStore } = await loadStore(dineIn());
    usePOSStore.setState({ tableOrder: { message: { name: 'x' } } as never });
    usePOSStore.getState().setSelectedOrderType('Take Away');
    const state = usePOSStore.getState();
    expect(state.selectedOrderType).toBe('Take Away');
    expect(state.selectedTable).toBeNull();
    expect(state.selectedRoom).toBeNull();
    expect(state.tableOrder).toBeNull();
  });

  it.each(['Delivery', 'Phone In'] as const)('is dropped for %s too', async (type) => {
    const { usePOSStore } = await loadStore(dineIn());
    usePOSStore.getState().setSelectedOrderType(type);
    expect(usePOSStore.getState().selectedTable).toBeNull();
  });

  it('stays for a dine in order', async () => {
    const { usePOSStore } = await loadStore(dineIn());
    usePOSStore.getState().setSelectedOrderType('Dine In');
    expect(usePOSStore.getState().selectedTable).toBe('MD-03');
  });

  it('stays with an order being edited that is switched between take away and delivery', async () => {
    const { usePOSStore } = await loadStore(
      dineIn({ selectedOrderType: 'Take Away', orderId: 'INV-00051', isUpdatingOrder: true })
    );
    usePOSStore.setState({ posProfile: { edit_order_type: 1 } as never });
    usePOSStore.getState().setSelectedOrderType('Delivery');
    expect(usePOSStore.getState().selectedOrderType).toBe('Delivery');
    expect(usePOSStore.getState().selectedTable).toBe('MD-03');
    expect(usePOSStore.getState().orderId).toBe('INV-00051');
  });

  it('is left behind by a page saved earlier with a table on a take away order', async () => {
    const { usePOSStore } = await loadStore(dineIn({ selectedOrderType: 'Take Away' }));
    const state = usePOSStore.getState();
    expect(state.selectedOrderType).toBe('Take Away');
    expect(state.selectedTable).toBeNull();
    expect(state.selectedRoom).toBeNull();
  });

  it('is kept on reload for a dine in order, and for an existing order that has one', async () => {
    expect((await loadStore(dineIn())).usePOSStore.getState().selectedTable).toBe('MD-03');
    const editing = await loadStore(
      dineIn({ selectedOrderType: 'Take Away', orderId: 'INV-00051', isUpdatingOrder: true })
    );
    expect(editing.usePOSStore.getState().selectedTable).toBe('MD-03');
  });
});

describe('closing a tab with unsaved changes', () => {
  it('throws the changes away and leaves the saved order alone', async () => {
    const fetchSpy = vi.fn();
    const { usePOSStore } = await loadStore(savedWhileEditing());
    vi.stubGlobal('fetch', fetchSpy);
    const store = usePOSStore.getState();
    const editingTab = store.activeTabId;
    // a second tab to land on
    store.addTab();
    usePOSStore.getState().switchTab(editingTab);
    usePOSStore.getState().closeTab(editingTab);
    const state = usePOSStore.getState();
    expect(state.tabOrder.map((tab) => tab.id)).not.toContain(editingTab);
    expect(state.tabOrder).toHaveLength(1);
    expect(state.activeOrders).toEqual([]);
    expect(state.isUpdatingOrder).toBe(false);
    expect(state.orderId).toBeNull();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('closing the only tab leaves one clean tab', async () => {
    const { usePOSStore } = await loadStore(savedWhileEditing());
    usePOSStore.getState().closeTab(usePOSStore.getState().activeTabId);
    const state = usePOSStore.getState();
    expect(state.tabOrder).toHaveLength(1);
    expect(state.isUpdatingOrder).toBe(false);
    expect(state.activeOrders).toEqual([]);
  });
});
