import { describe, expect, it, vi } from 'vitest';
import { drawerAfterPayment, finishPayment, openDrawerByHand, serverPrint, showsDrawerButton } from './drawer';

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

describe('finishing a payment', () => {
  const never = () => new Promise<never>(() => undefined);

  it('closes the payment window at once, however long the drawer takes', () => {
    const closed = vi.fn();
    const notify = vi.fn();
    finishPayment({ openDrawer: never, notify, onClosed: closed, table: 'MD-03', invoice: 'INV-1' });
    expect(closed).toHaveBeenCalledTimes(1); // synchronously: the cashier does not wait for the drawer
    expect(notify).not.toHaveBeenCalled();
  });

  it('says so, with the table, when the drawer did not open (after the window is closed)', async () => {
    const notify = vi.fn();
    const closed = vi.fn();
    finishPayment({
      openDrawer: async () => ({ ok: false, opened: false, message: '引き出しが開きませんでした。鍵で開けてください。' }),
      notify,
      onClosed: closed,
      table: 'MD-03',
      invoice: 'INV-1',
    });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(closed).toHaveBeenCalledTimes(1);
    expect(notify).toHaveBeenCalledTimes(1);
    expect(notify).toHaveBeenCalledWith('MD-03：引き出しが開きませんでした。鍵で開けてください。', 'drawer-INV-1');
  });

  it('names the invoice when there is no table (a take-away)', async () => {
    const notify = vi.fn();
    finishPayment({ openDrawer: async () => ({ ok: false, opened: false, message: 'x' }), notify, onClosed: () => undefined, table: null, invoice: 'INV-9' });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(notify).toHaveBeenCalledWith('INV-9：x', 'drawer-INV-9');
  });

  it('says nothing when the drawer opened, or did not have to (a card)', async () => {
    const notify = vi.fn();
    for (const answer of [{ ok: true, opened: true, message: '' }, { ok: true, opened: false, message: '' }]) {
      finishPayment({ openDrawer: async () => answer, notify, onClosed: () => undefined, table: 'MD-03', invoice: 'INV-1' });
    }
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(notify).not.toHaveBeenCalled();
  });

  it('does not ask for the drawer when the server does not print, and still closes', () => {
    const closed = vi.fn();
    finishPayment({ openDrawer: null, notify: vi.fn(), onClosed: closed, table: 'MD-03', invoice: 'INV-1' });
    expect(closed).toHaveBeenCalledTimes(1);
  });

  it('a drawer call that breaks is a message too, never an unhandled error', async () => {
    const notify = vi.fn();
    finishPayment({
      openDrawer: async () => {
        throw new Error('boom');
      },
      notify,
      onClosed: () => undefined,
      table: 'MD-03',
      invoice: 'INV-1',
    });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(notify).toHaveBeenCalledTimes(1);
    expect(notify.mock.calls[0][0]).toContain('MD-03');
  });
});

describe('the offer of the receipt, next to the drawer (2026-11-20)', () => {
  it('is made after the window is closed, once, whether or not the drawer is asked for', () => {
    for (const openDrawer of [null, async () => ({ ok: true, opened: true, message: '' })]) {
      const order: string[] = [];
      finishPayment({
        openDrawer,
        notify: vi.fn(),
        onClosed: () => order.push('closed'),
        offerReceipt: () => order.push('offer'),
        table: 'MD-06',
        invoice: 'INV-1',
      });
      expect(order).toEqual(['closed', 'offer']);
    }
  });

  it('does not change the red message of a drawer that did not open', async () => {
    const notify = vi.fn();
    const offer = vi.fn();
    finishPayment({
      openDrawer: async () => ({ ok: false, opened: false, message: '引き出しが開きませんでした。鍵で開けてください。' }),
      notify,
      onClosed: () => undefined,
      offerReceipt: offer,
      table: 'MD-06',
      invoice: 'INV-1',
    });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(offer).toHaveBeenCalledTimes(1);
    expect(notify).toHaveBeenCalledTimes(1);
    expect(notify).toHaveBeenCalledWith('MD-06：引き出しが開きませんでした。鍵で開けてください。', 'drawer-INV-1');
  });

  it('an offer that breaks does not stop the window from closing or the drawer from being asked', async () => {
    const closed = vi.fn();
    const openDrawer = vi.fn(async () => ({ ok: true, opened: true, message: '' }));
    expect(() =>
      finishPayment({
        openDrawer,
        notify: vi.fn(),
        onClosed: closed,
        offerReceipt: () => {
          throw new Error('boom');
        },
        table: null,
        invoice: 'INV-1',
      })
    ).not.toThrow();
    expect(closed).toHaveBeenCalledTimes(1);
    expect(openDrawer).toHaveBeenCalledTimes(1);
  });

  it('is optional: a payment without it behaves as before', () => {
    const closed = vi.fn();
    finishPayment({ openDrawer: null, notify: vi.fn(), onClosed: closed, table: 'MD-03', invoice: 'INV-1' });
    expect(closed).toHaveBeenCalledTimes(1);
  });
});
