import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../lib/menu-api', () => ({ getRestaurantMenu: vi.fn(async () => []), getAggregatorMenu: vi.fn(async () => []) }));
vi.mock('../lib/customer-api', () => ({
  getCustomerGroups: vi.fn(async () => []),
  getCustomerTerritories: vi.fn(async () => []),
  getCustomerRecord: vi.fn(async () => ({ name: '一般のお客様', customer_name: '一般のお客様', mobile_number: null, disabled: 0 })),
}));

import { usePOSStore } from './pos-store';

const DEFAULT = { id: '一般のお客様', name: '一般のお客様', phone: '' };
const NAMED = { id: 'customer1 - 12', name: 'customer1', phone: '080' };

describe('changing the order type in the store', () => {
  beforeEach(() => {
    usePOSStore.setState({
      defaultCustomer: DEFAULT,
      selectedCustomer: DEFAULT,
      selectedOrderType: 'Take Away',
      activeOrders: [],
      isUpdatingOrder: false,
      posProfile: null,
    });
  });

  it.each(['Delivery', 'Phone In'] as const)('drops the default customer for %s', (type) => {
    usePOSStore.getState().setSelectedOrderType(type);
    expect(usePOSStore.getState().selectedOrderType).toBe(type);
    expect(usePOSStore.getState().selectedCustomer).toBeNull();
  });

  it('keeps a customer the cashier chose for delivery', () => {
    usePOSStore.setState({ selectedCustomer: NAMED });
    usePOSStore.getState().setSelectedOrderType('Delivery');
    expect(usePOSStore.getState().selectedCustomer).toEqual(NAMED);
  });

  it('fills the default customer again when coming back to take away', () => {
    usePOSStore.getState().setSelectedOrderType('Delivery');
    usePOSStore.getState().setSelectedOrderType('Take Away');
    expect(usePOSStore.getState().selectedCustomer).toEqual(DEFAULT);
  });

  it('from loading the profile to leaving the default customer for delivery', async () => {
    usePOSStore.setState({ defaultCustomer: null, selectedCustomer: null, posProfile: { customer: '一般のお客様' } as never });
    await usePOSStore.getState().fetchDefaultCustomer();
    expect(usePOSStore.getState().selectedCustomer).toEqual(DEFAULT);
    usePOSStore.getState().setSelectedOrderType('Delivery');
    expect(usePOSStore.getState().selectedCustomer).toBeNull();
    usePOSStore.getState().setSelectedOrderType('Phone In');
    expect(usePOSStore.getState().selectedCustomer).toBeNull();
  });

  it('still drops the default customer for delivery when the default customer was not loaded', () => {
    // the profile names the default customer, but its record did not load (failed fetch, stale cache)
    usePOSStore.setState({
      defaultCustomer: null,
      selectedCustomer: DEFAULT,
      posProfile: { customer: '一般のお客様' } as never,
    });
    usePOSStore.getState().setSelectedOrderType('Delivery');
    expect(usePOSStore.getState().selectedCustomer).toBeNull();
  });
});
