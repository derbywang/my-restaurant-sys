import { describe, expect, it } from 'vitest';

import {
  customerAfterOrderTypeChange,
  customerId,
  defaultCustomerOf,
  freshOrderCustomer,
  isFreshOrder,
  toDefaultCustomer,
  type CustomerRecord,
} from './default-customer';

const DEFAULT = { id: '一般のお客様', name: '一般のお客様', phone: '' };
const NAMED = { id: 'customer1 - 12', name: 'customer1', phone: '08022224444' };

describe('toDefaultCustomer', () => {
  it('uses the docname as id and the customer name as name; no phone is an empty string', () => {
    const record: CustomerRecord = { name: '一般のお客様', customer_name: '一般のお客様', mobile_number: null };
    expect(toDefaultCustomer(record)).toEqual(DEFAULT);
  });

  it('keeps the docname apart from the customer name', () => {
    const record: CustomerRecord = { name: 'customer1 - 12', customer_name: 'customer1', mobile_number: '080' };
    expect(toDefaultCustomer(record)).toEqual({ id: 'customer1 - 12', name: 'customer1', phone: '080' });
  });

  it('is null when the profile has no customer, the customer is missing or disabled', () => {
    expect(toDefaultCustomer(null)).toBeNull();
    expect(toDefaultCustomer(undefined)).toBeNull();
    expect(toDefaultCustomer({ name: 'x', customer_name: 'x', mobile_number: '', disabled: 1 })).toBeNull();
  });
});

describe('freshOrderCustomer', () => {
  it.each(['Dine In', 'Take Away'] as const)('%s starts with the default customer', (type) => {
    expect(freshOrderCustomer(DEFAULT, type)).toEqual(DEFAULT);
  });

  it.each(['Delivery', 'Phone In'] as const)('%s starts without a customer', (type) => {
    expect(freshOrderCustomer(DEFAULT, type)).toBeNull();
  });

  it('is null on a site without a default customer', () => {
    expect(freshOrderCustomer(null, 'Take Away')).toBeNull();
  });
});

describe('customerAfterOrderTypeChange', () => {
  it('keeps the customer when switching between dine in and take away', () => {
    expect(customerAfterOrderTypeChange(NAMED, DEFAULT, 'Take Away')).toEqual(NAMED);
    expect(customerAfterOrderTypeChange(DEFAULT, DEFAULT, 'Dine In')).toEqual(DEFAULT);
  });

  it('drops the default customer when switching to delivery or phone in', () => {
    expect(customerAfterOrderTypeChange(DEFAULT, DEFAULT, 'Delivery')).toBeNull();
    expect(customerAfterOrderTypeChange(DEFAULT, DEFAULT, 'Phone In')).toBeNull();
  });

  it('keeps a customer the cashier chose when switching to delivery or phone in', () => {
    expect(customerAfterOrderTypeChange(NAMED, DEFAULT, 'Delivery')).toEqual(NAMED);
    expect(customerAfterOrderTypeChange(NAMED, DEFAULT, 'Phone In')).toEqual(NAMED);
  });

  it('fills the default customer when coming back to dine in or take away without one', () => {
    expect(customerAfterOrderTypeChange(null, DEFAULT, 'Take Away')).toEqual(DEFAULT);
    expect(customerAfterOrderTypeChange(null, DEFAULT, 'Dine In')).toEqual(DEFAULT);
  });

  it('does not fill a customer for delivery or phone in, or without a default customer', () => {
    expect(customerAfterOrderTypeChange(null, DEFAULT, 'Delivery')).toBeNull();
    expect(customerAfterOrderTypeChange(null, null, 'Take Away')).toBeNull();
  });

  it('leaves the customer alone for aggregators', () => {
    expect(customerAfterOrderTypeChange(null, DEFAULT, 'Aggregators')).toBeNull();
    expect(customerAfterOrderTypeChange(NAMED, DEFAULT, 'Aggregators')).toEqual(NAMED);
    expect(customerAfterOrderTypeChange(DEFAULT, DEFAULT, 'Aggregators')).toEqual(DEFAULT);
  });
});

describe('isFreshOrder', () => {
  const fresh = { activeOrders: [], selectedCustomer: null, isUpdatingOrder: false, orderLoading: false };

  it('is true for an empty tab with no customer', () => {
    expect(isFreshOrder(fresh)).toBe(true);
  });

  it('is false when the tab has items, a customer, an order being updated or is loading', () => {
    expect(isFreshOrder({ ...fresh, activeOrders: [{}] as never[] })).toBe(false);
    expect(isFreshOrder({ ...fresh, selectedCustomer: NAMED })).toBe(false);
    expect(isFreshOrder({ ...fresh, isUpdatingOrder: true })).toBe(false);
    expect(isFreshOrder({ ...fresh, orderLoading: true })).toBe(false);
  });
});

describe('customerId', () => {
  it('is the docname, not the customer name (two customers can share a name)', () => {
    expect(customerId(NAMED)).toBe('customer1 - 12');
  });

  it('is undefined without a customer', () => {
    expect(customerId(null)).toBeUndefined();
    expect(customerId(undefined)).toBeUndefined();
  });
});

describe('defaultCustomerOf', () => {
  it('is the loaded default customer', () => {
    expect(defaultCustomerOf(DEFAULT, 'other')).toEqual(DEFAULT);
  });

  it('falls back to the customer the POS Profile names when the record did not load', () => {
    expect(defaultCustomerOf(null, '一般のお客様')).toEqual({ id: '一般のお客様', name: '一般のお客様', phone: '' });
  });

  it('is null when the profile names no customer', () => {
    expect(defaultCustomerOf(null, null)).toBeNull();
    expect(defaultCustomerOf(null, undefined)).toBeNull();
    expect(defaultCustomerOf(null, '')).toBeNull();
  });
});
