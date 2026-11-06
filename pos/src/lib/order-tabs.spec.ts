import { describe, expect, it } from 'vitest';

import { tabCloseAction, tableForSubmit } from './order-tabs';

describe('tableForSubmit', () => {
  it('sends the table only for a dine in order', () => {
    expect(tableForSubmit('Dine In', 'MD-03')).toBe('MD-03');
  });

  it.each(['Take Away', 'Delivery', 'Phone In', 'Aggregators'] as const)(
    'sends no table for %s, whatever table was picked before',
    (type) => {
      expect(tableForSubmit(type, 'MD-03')).toBeUndefined();
    }
  );

  it('sends nothing when there is no table', () => {
    expect(tableForSubmit('Dine In', null)).toBeUndefined();
    expect(tableForSubmit('Take Away', null)).toBeUndefined();
  });
});

describe('tabCloseAction', () => {
  const base = { cartIsEmpty: false, isUpdatingOrder: false, cartHash: 'a', originalCartHash: 'a' };

  it('closes an empty tab at once', () => {
    expect(tabCloseAction({ ...base, cartIsEmpty: true })).toBe('close');
    expect(tabCloseAction({ ...base, cartIsEmpty: true, isUpdatingOrder: true, cartHash: 'b' })).toBe('close');
  });

  it('asks before throwing away a new cart that has items', () => {
    expect(tabCloseAction(base)).toBe('remove_cart');
  });

  it('closes an edited order at once when nothing was changed', () => {
    expect(tabCloseAction({ ...base, isUpdatingOrder: true })).toBe('close');
  });

  it('asks about unsaved changes when an edited order was changed', () => {
    expect(tabCloseAction({ ...base, isUpdatingOrder: true, cartHash: 'b' })).toBe('unsaved_changes');
  });
});

import { ROUTE_AFTER_SUBMIT } from './order-tabs';

describe('after an order was sent', () => {
  it('the cashier lands on the table page', () => {
    expect(ROUTE_AFTER_SUBMIT).toBe('/tables');
  });
});
