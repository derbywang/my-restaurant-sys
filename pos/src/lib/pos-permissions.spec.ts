import { describe, expect, it } from 'vitest';

import {
  NO_PERMISSIONS,
  canShowDiscount,
  friendlyError,
  normalizePermissions,
} from './pos-permissions';

const CASHIER = {
  take_orders: true,
  print_bill: true,
  settle_payment: true,
  cancel_order: true,
  apply_discount: true,
  merge_bills: true,
  unmerge_bills: true,
  split_bill: true,
  open_shift: true,
  close_shift: true,
};

describe('normalizePermissions', () => {
  it('takes what the server says', () => {
    expect(normalizePermissions(CASHIER)).toEqual(CASHIER);
  });

  it('is only true for true: anything else, or a missing key, is a no', () => {
    expect(normalizePermissions({ ...CASHIER, settle_payment: 1, split_bill: 'yes', merge_bills: undefined })).toEqual({
      ...CASHIER,
      settle_payment: false,
      split_bill: false,
      merge_bills: false,
    });
  });

  it('is a no for everything when the answer is not an object', () => {
    expect(normalizePermissions(null)).toEqual(NO_PERMISSIONS);
    expect(normalizePermissions('x')).toEqual(NO_PERMISSIONS);
    expect(Object.values(NO_PERMISSIONS).every((value) => value === false)).toBe(true);
  });

  it('keeps no unknown keys', () => {
    expect(Object.keys(normalizePermissions({ ...CASHIER, admin: true }))).toEqual(Object.keys(CASHIER));
  });
});

describe('canShowDiscount', () => {
  it('needs the permission and the POS Profile switch', () => {
    expect(canShowDiscount(CASHIER, 1)).toBe(true);
    expect(canShowDiscount(CASHIER, 0)).toBe(false);
    expect(canShowDiscount(CASHIER, undefined)).toBe(false);
    expect(canShowDiscount({ ...CASHIER, apply_discount: false }, 1)).toBe(false);
  });

  it('is hidden until the permissions are known', () => {
    expect(canShowDiscount(null, 1)).toBe(false);
  });
});

describe('friendlyError', () => {
  const t = (key: string) => `[${key}]`;

  it('says in the user language that the user may not, whatever the server wrote', () => {
    const err = { exc_type: 'PermissionError', _server_messages: '["{\\"message\\": \\"User x does not have doctype access\\"}"]' };
    expect(friendlyError(err, 'payment failed', t)).toBe('[errors.not_permitted_billing]');
  });

  it('shows what the server said for other errors', () => {
    const err = { _server_messages: '["{\\"message\\": \\"Stock is short\\"}"]' };
    expect(friendlyError(err, 'payment failed', t)).toBe('Stock is short');
  });

  it('falls back when there is nothing to show', () => {
    expect(friendlyError(undefined, 'payment failed', t)).toBe('payment failed');
  });
});
