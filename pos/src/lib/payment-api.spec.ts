import { beforeEach, describe, expect, it, vi } from 'vitest';

const get = vi.fn();
vi.mock('@ury/core', () => ({ call: { get: (...a: unknown[]) => get(...a) } }));

import { getPaymentModeTypes, getPaymentModes } from './payment-api';

function stubStorage(initial: Record<string, string>) {
  const data = { ...initial };
  vi.stubGlobal('sessionStorage', {
    getItem: (k: string) => data[k] ?? null,
    setItem: (k: string, v: string) => {
      data[k] = v;
    },
    removeItem: (k: string) => {
      delete data[k];
    },
  });
}

const OLD = [{ mode_of_payment: '現金', opening_amount: 0, type: 'Cash' }];
const NEW = [...OLD, { mode_of_payment: 'PayPay', opening_amount: 0, type: 'Bank' }];

// The payment modes were kept in the tab and used whenever they were there: a mode added after the register was opened
// was not offered until the tab was closed (2026-11-15).
describe('the payment modes', () => {
  beforeEach(() => {
    get.mockReset();
  });

  it('are the ones the server has now, not the list kept in the tab', async () => {
    stubStorage({ payment_mode_list: JSON.stringify(OLD) });
    get.mockResolvedValue({ message: NEW });
    expect(await getPaymentModes()).toEqual(['現金', 'PayPay']);
  });

  it('are the list kept in the tab when the server cannot be reached', async () => {
    stubStorage({ payment_mode_list: JSON.stringify(OLD) });
    get.mockRejectedValue(new Error('offline'));
    expect(await getPaymentModes()).toEqual(['現金']);
  });

  it('names and types are one request when they are asked for together', async () => {
    stubStorage({});
    get.mockResolvedValue({ message: NEW });
    const [names, types] = await Promise.all([getPaymentModes(), getPaymentModeTypes()]);
    expect(names).toEqual(['現金', 'PayPay']);
    expect(types).toEqual({ 現金: 'Cash', PayPay: 'Bank' });
    expect(get).toHaveBeenCalledTimes(1);
  });
});
