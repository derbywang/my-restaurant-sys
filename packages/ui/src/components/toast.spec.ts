import { beforeEach, describe, expect, it, vi } from 'vitest';

const error = vi.fn();
const success = vi.fn();
vi.mock('react-toastify', () => ({
  toast: { error: (...args: unknown[]) => error(...args), success: (...args: unknown[]) => success(...args), warning: vi.fn(), info: vi.fn(), dismiss: vi.fn() },
  ToastContainer: () => null,
}));

import { showToast } from './toast';

describe('a red message that stays', () => {
  beforeEach(() => error.mockClear());

  it('does not go away by itself, so the next order cannot hide it', () => {
    showToast.errorStay('MD-03：引き出しが開きませんでした。鍵で開けてください。', 'drawer-INV-1');
    const [message, options] = error.mock.calls[0];
    expect(message).toContain('引き出し');
    expect(options.autoClose).toBe(false);
    expect(options.closeOnClick).toBe(true);
    expect(options.className).toContain('toast-error-sticky');
  });

  it('has an id of its own, so the same message does not pile up', () => {
    showToast.errorStay('x', 'drawer-INV-1');
    expect(error.mock.calls[0][1].toastId).toBe('drawer-INV-1');
  });

  it('the usual red message still goes away after two seconds', () => {
    showToast.error('x');
    expect(error.mock.calls[0][1].autoClose).toBe(2000);
  });
});

describe('a message with a button that goes away by itself (the receipt after a payment)', () => {
  beforeEach(() => success.mockClear());

  it('stays a few seconds, long enough to press, and has an id of its own', () => {
    showToast.withAction('INV-1（MD-06）：お会計が済みました', '領収書を印刷', () => undefined, 'receipt-INV-1');
    const [content, options] = success.mock.calls[0];
    expect(content).toBeTruthy();
    expect(options.toastId).toBe('receipt-INV-1');
    expect(options.autoClose).toBeGreaterThanOrEqual(6000);
    expect(options.autoClose).toBeLessThanOrEqual(15000);
    expect(options.closeOnClick).toBe(false); // a touch beside the button must not make it disappear
  });
});
