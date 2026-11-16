import { describe, expect, it, vi } from 'vitest';
import { drawerAfterPayment, openDrawerByHand, serverPrint, showsDrawerButton } from './drawer';

const post = (answer: unknown) => vi.fn(async () => ({ message: answer }));
const refusing = () => vi.fn(async () => {
  throw new Error('network down');
});

describe('the drawer button', () => {
  it('shows only for who may take the money and only when the server prints', () => {
    expect(showsDrawerButton({ settle_payment: true }, 'server')).toBe(true);
    expect(showsDrawerButton({ settle_payment: false }, 'server')).toBe(false);
    expect(showsDrawerButton({ settle_payment: true }, 'qz')).toBe(false);
    expect(showsDrawerButton(null, 'server')).toBe(false);
  });

  it('asks the server and returns its answer', async () => {
    const send = post({ ok: true, message: '' });
    expect(await openDrawerByHand(send)).toEqual({ ok: true, message: '' });
    expect(send).toHaveBeenCalledWith('ury.ury.api.receipt_print.open_drawer', {});
  });

  it('turns a network failure into a sentence for the cashier', async () => {
    const result = await openDrawerByHand(refusing());
    expect(result.ok).toBe(false);
    expect(result.message).toContain('鍵');
  });
});

describe('the drawer after a payment', () => {
  it('names the invoice that was paid', async () => {
    const send = post({ ok: true, opened: true, message: '' });
    expect(await drawerAfterPayment('INV-1', send)).toEqual({ ok: true, opened: true, message: '' });
    expect(send).toHaveBeenCalledWith('ury.ury.api.receipt_print.drawer_for_settlement', { invoice: 'INV-1' });
  });

  it('never throws: a payment that went through stays paid', async () => {
    const result = await drawerAfterPayment('INV-1', refusing());
    expect(result.ok).toBe(false);
    expect(result.opened).toBe(false);
    expect(result.message).toContain('鍵');
  });

  it('says nothing when the drawer did not have to open (card)', async () => {
    const result = await drawerAfterPayment('INV-1', post({ ok: true, opened: false, message: '' }));
    expect(result.opened).toBe(false);
    expect(result.message).toBe('');
  });
});

describe('printing through the server', () => {
  it('prints, then lets the invoice know it was printed', async () => {
    const send = post({ ok: true, message: '' });
    const printed = vi.fn(async () => undefined);
    await serverPrint('INV-1', 'URY JP Receipt', send, printed);
    expect(send).toHaveBeenCalledWith('ury.ury.api.receipt_print.print_bill', { invoice: 'INV-1', print_format: 'URY JP Receipt' });
    expect(printed).toHaveBeenCalledWith('INV-1');
  });

  it('shows the printer\'s trouble and does not mark the bill as printed', async () => {
    const printed = vi.fn(async () => undefined);
    await expect(serverPrint('INV-1', 'f', post({ ok: false, message: '用紙がありません' }), printed)).rejects.toThrow('用紙がありません');
    expect(printed).not.toHaveBeenCalled();
  });
});
