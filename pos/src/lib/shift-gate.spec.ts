import { describe, expect, it } from 'vitest';

import { modeTypesOf, RECHECK_MS, routeForOpening } from './shift-gate';
import { NO_PERMISSIONS, type PosPermissions } from './pos-permissions';

const waiter: PosPermissions = { ...NO_PERMISSIONS, take_orders: true };
const cashier: PosPermissions = { ...NO_PERMISSIONS, take_orders: true, settle_payment: true, open_shift: true, close_shift: true };

describe('which way the POS opens', () => {
  it('waits for the permissions: neither lets the user in nor shows the opening screen', () => {
    expect(routeForOpening(null, null)).toBe('loading');
    expect(routeForOpening(null, { open: true, opened_by: 'cashier@example.com' })).toBe('loading');
  });

  it('keeps the cashier on the screen of her own shift', () => {
    expect(routeForOpening(cashier, null)).toBe('own_shift');
    expect(routeForOpening(cashier, { open: false, opened_by: null })).toBe('own_shift');
  });

  it('keeps someone who may open a shift on the screen of her own shift, even if she also takes orders', () => {
    expect(routeForOpening({ ...waiter, open_shift: true }, null)).toBe('own_shift');
  });

  it('lets the waiter in when the register of the shop is open, whoever opened it', () => {
    expect(routeForOpening(waiter, { open: true, opened_by: 'cashier@example.com' })).toBe('open');
  });

  it('shows the waiter the waiting page when the register is not open', () => {
    expect(routeForOpening(waiter, { open: false, opened_by: null })).toBe('closed');
  });

  it('does not show the waiting page before the answer is there', () => {
    expect(routeForOpening(waiter, null)).toBe('loading');
  });

  it('asks again every 30 seconds', () => {
    expect(RECHECK_MS).toBe(30_000);
  });
});

describe('the type of each payment mode on the opening screen', () => {
  it('maps the name to the type', () => {
    expect(modeTypesOf([{ mode_of_payment: 'Cash', type: 'Cash' }, { mode_of_payment: 'PayPay', type: 'Bank' }])).toEqual({
      Cash: 'Cash',
      PayPay: 'Bank',
    });
  });

  it('leaves out a mode whose type the server did not give', () => {
    expect(modeTypesOf([{ mode_of_payment: 'Cash' }])).toEqual({});
  });
});
