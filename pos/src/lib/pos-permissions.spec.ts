import { describe, expect, it } from 'vitest';

import {
  NO_PERMISSIONS,
  canShowDiscount,
  canViewDashboard,
  friendlyError,
  isWaiterOnly,
  showsWaiterScreenLink,
  showsRegisterLink,
  leaveForRegister,
  REGISTER_URL,
  normalizePermissions,
} from './pos-permissions';

const CASHIER = {
  take_orders: true,
  print_bill: true,
  settle_payment: true,
  view_dashboard: true,
  cancel_order: true,
  apply_discount: true,
  merge_bills: true,
  unmerge_bills: true,
  split_bill: true,
  reduce_sent_items: true,
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

describe('the waiter screen', () => {
  const waiter = { ...NO_PERMISSIONS, take_orders: true, print_bill: true };
  const cashier = { ...waiter, settle_payment: true, open_shift: true, close_shift: true };

  it('is where someone who only takes orders lands', () => {
    expect(isWaiterOnly(waiter)).toBe(true);
    expect(isWaiterOnly(cashier)).toBe(false);
    expect(isWaiterOnly({ ...waiter, settle_payment: true })).toBe(false);
    expect(isWaiterOnly({ ...waiter, open_shift: true })).toBe(false);
  });

  it('is nowhere for someone who cannot take orders, or whose permissions are not known', () => {
    expect(isWaiterOnly(null)).toBe(false);
    expect(isWaiterOnly(NO_PERMISSIONS)).toBe(false);
    expect(showsWaiterScreenLink(null)).toBe(false);
    expect(showsWaiterScreenLink(NO_PERMISSIONS)).toBe(false);
  });

  it('is offered in the menu to those who work at the register too, not to the waiter who is there already', () => {
    expect(showsWaiterScreenLink(cashier)).toBe(true);
    expect(showsWaiterScreenLink(waiter)).toBe(false);
  });
});

describe('the dashboard page', () => {
  it('is shown only when the server says the user may see the sales', () => {
    expect(canViewDashboard({ ...NO_PERMISSIONS, view_dashboard: true })).toBe(true);
    expect(canViewDashboard({ ...NO_PERMISSIONS, take_orders: true, print_bill: true })).toBe(false); // a waiter
    expect(canViewDashboard(NO_PERMISSIONS)).toBe(false);
  });

  it('is not shown while the permissions are not known', () => {
    expect(canViewDashboard(null)).toBe(false);
  });

  it('is a no when the answer lacks the key (an old server)', () => {
    expect(normalizePermissions({ take_orders: true, settle_payment: true }).view_dashboard).toBe(false);
  });
});

describe('the way back to the register from the waiter screen', () => {
  const waiter = { ...NO_PERMISSIONS, take_orders: true, print_bill: true };

  it('is offered to who may take the money, not to a waiter, not before the permissions are known', () => {
    expect(showsRegisterLink(normalizePermissions(CASHIER))).toBe(true);
    expect(showsRegisterLink(waiter)).toBe(false);
    expect(showsRegisterLink(NO_PERMISSIONS)).toBe(false);
    expect(showsRegisterLink(null)).toBe(false);
  });

  it('goes to the register screen at once when nothing waits to be sent', () => {
    const went: string[] = [];
    let asked = 0;
    leaveForRegister({ hasUnsent: false, ask: () => asked++, go: (url) => went.push(url) });
    expect(went).toEqual([REGISTER_URL]);
    expect(asked).toBe(0);
    expect(REGISTER_URL).toBe('/pos/pos');
  });

  it('asks first when dishes were not sent yet (leaving throws them away)', () => {
    const went: string[] = [];
    let asked = 0;
    leaveForRegister({ hasUnsent: true, ask: () => asked++, go: (url) => went.push(url) });
    expect(went).toEqual([]);
    expect(asked).toBe(1);
  });
});

describe('the words of the way back', () => {
  it('are there in the four languages of the staff', async () => {
    for (const language of ['ja', 'en', 'zh', 'ko']) {
      const messages = (await import(`../i18n/locales/${language}.json`)).default;
      for (const key of ['back_to_register', 'register_unsent_message', 'register_anyway']) {
        expect(messages.captain[key], `${language} captain.${key}`).toBeTruthy();
      }
    }
    const ja = (await import('../i18n/locales/ja.json')).default;
    expect(ja.captain.back_to_register).toBe('レジに戻る');
  });
});
