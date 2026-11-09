import { describe, expect, it } from 'vitest';

import { STAMP_THRESHOLD, stampNotice } from './stamp-duty';

const types = { Cash: 'Cash', 'クレジットカード': 'Bank', PayPay: 'Bank' };

describe('stampNotice (same rule as stamp_duty_needed in receipt.py)', () => {
  it('the threshold is fifty thousand', () => {
    expect(STAMP_THRESHOLD).toBe(50000);
  });

  it('all cash: counts the amount without the tax', () => {
    expect(stampNotice([{ mode_of_payment: 'Cash', amount: 55000 }], types, 55000, 50000)).toMatchObject({ needed: true, netCash: 50000 });
    expect(stampNotice([{ mode_of_payment: 'Cash', amount: 54998 }], types, 54998, 49999).needed).toBe(false);
  });

  it('takes the change off the cash handed over', () => {
    const notice = stampNotice([{ mode_of_payment: 'Cash', amount: 60000 }], types, 55000, 50000);
    expect(notice).toMatchObject({ needed: true, cashPaid: 55000 });
    expect(stampNotice([{ mode_of_payment: 'Cash', amount: 60000 }], types, 44000, 40000).needed).toBe(false);
  });

  it('no cash, no stamp', () => {
    expect(stampNotice([{ mode_of_payment: 'クレジットカード', amount: 110000 }], types, 110000, 100000).needed).toBe(false);
  });

  it('a mixed payment: the cash part by its share without the tax', () => {
    const mix = (cash: number, card: number) =>
      stampNotice([{ mode_of_payment: 'Cash', amount: cash }, { mode_of_payment: 'クレジットカード', amount: card }], types, 110000, 100000);
    expect(mix(55000, 55000)).toMatchObject({ needed: true, netCash: 50000 });
    expect(mix(54000, 56000).needed).toBe(false);
  });

  it('nothing entered or nothing due is no stamp', () => {
    expect(stampNotice([], types, 55000, 50000).needed).toBe(false);
    expect(stampNotice([{ mode_of_payment: 'Cash', amount: 60000 }], types, 0, 0).needed).toBe(false);
  });

  it('without the types of the modes (an old session) there is no notice', () => {
    expect(stampNotice([{ mode_of_payment: 'Cash', amount: 60000 }], {}, 55000, 50000).needed).toBe(false);
  });
});
