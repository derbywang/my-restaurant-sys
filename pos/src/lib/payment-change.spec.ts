import { describe, expect, it } from 'vitest';
import { checkPayments, defaultCashMode } from './payment-change';

const types = { Cash: 'Cash', クレジットカード: 'Bank', PayPay: 'Bank' };

describe('checkPayments', () => {
  it('exact card payment: no change, no error', () => {
    expect(checkPayments([{ mode_of_payment: 'クレジットカード', amount: 2710 }], 2710, types)).toEqual({
      change: 0,
      short: 0,
      error: null,
    });
  });

  it('cash over the amount is change', () => {
    expect(checkPayments([{ mode_of_payment: 'Cash', amount: 3000 }], 2750, types)).toEqual({
      change: 250,
      short: 0,
      error: null,
    });
  });

  it('cash and card adding up exactly', () => {
    expect(
      checkPayments(
        [
          { mode_of_payment: 'Cash', amount: 1000 },
          { mode_of_payment: 'クレジットカード', amount: 1710 },
        ],
        2710,
        types
      )
    ).toEqual({ change: 0, short: 0, error: null });
  });

  it('change out of the cash handed over is fine next to a card', () => {
    const result = checkPayments(
      [
        { mode_of_payment: 'Cash', amount: 1200 },
        { mode_of_payment: 'クレジットカード', amount: 1710 },
      ],
      2710,
      types
    );
    expect(result).toEqual({ change: 200, short: 0, error: null });
  });

  it('a card cannot be charged over the amount', () => {
    expect(checkPayments([{ mode_of_payment: 'クレジットカード', amount: 3000 }], 2710, types)).toMatchObject({
      change: 290,
      error: 'change_not_cash',
    });
  });

  it('the change cannot be more than the cash handed over', () => {
    expect(
      checkPayments(
        [
          { mode_of_payment: 'Cash', amount: 100 },
          { mode_of_payment: 'PayPay', amount: 2800 },
        ],
        2710,
        types
      )
    ).toMatchObject({ change: 190, error: 'change_not_cash' });
  });

  it('reports what is still short', () => {
    expect(checkPayments([{ mode_of_payment: 'Cash', amount: 1000 }], 2710, types)).toEqual({
      change: 0,
      short: 1710,
      error: null,
    });
  });

  it('without the payment types the rule is left to the server', () => {
    expect(checkPayments([{ mode_of_payment: 'クレジットカード', amount: 3000 }], 2710, {})).toMatchObject({
      change: 290,
      error: null,
    });
  });
});

describe('defaultCashMode', () => {
  it('is the mode of type Cash, whatever it is called (「現金」 on a Japanese site)', () => {
    expect(defaultCashMode(['クレジットカード', '現金'], { クレジットカード: 'Bank', 現金: 'Cash' })).toBe('現金');
    expect(defaultCashMode(['Cash', 'PayPay'], { Cash: 'Cash', PayPay: 'Bank' })).toBe('Cash');
  });

  it('is undefined when the profile has no cash mode: nothing is filled in', () => {
    expect(defaultCashMode(['PayPay'], { PayPay: 'Bank' })).toBeUndefined();
  });

  it('falls back to the mode called Cash when the types are not known (an old session)', () => {
    expect(defaultCashMode(['PayPay', 'Cash'], {})).toBe('Cash');
    expect(defaultCashMode(['PayPay', '現金'], {})).toBeUndefined();
  });
});
