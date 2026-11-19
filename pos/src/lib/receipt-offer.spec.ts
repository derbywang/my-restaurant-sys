import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it, vi } from 'vitest';

import en from '../i18n/locales/en.json';
import ja from '../i18n/locales/ja.json';
import ko from '../i18n/locales/ko.json';
import zh from '../i18n/locales/zh.json';
import { offerReceipt } from './receipt-offer';

// 2026-11-20 (browser test C9): nothing tells the cashier that the receipt is not printed after a payment. After a payment the
// cashier is offered 「領収書を印刷」 for a few seconds; it prints only when pressed, through the printing of a paid invoice
// (the drawer stays shut), and a failure is a red message that stays, with the table.
const texts = {
  offer: (name: string) => `${name}：お会計が済みました`,
  button: '領収書を印刷',
  failed: (reason: string) => `領収書を印刷できませんでした：${reason}`,
};

function run(print: () => Promise<unknown>, table: string | null = 'MD-06', extra: Record<string, unknown> = {}) {
  const shown: Array<{ message: string; button: string; press: () => void; id: string }> = [];
  const failures: Array<{ message: string; id: string }> = [];
  offerReceipt({
    invoice: 'INV-121',
    table,
    print,
    show: (message, button, press, id) => shown.push({ message, button, press, id }),
    notifyFailure: (message, id) => failures.push({ message, id }),
    texts,
    ...extra,
  });
  return { shown, failures };
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

describe('the offer after a payment', () => {
  it('says the bill is paid, with the invoice and the table, and a button; nothing is printed yet', () => {
    const print = vi.fn(async () => undefined);
    const { shown } = run(print);
    expect(shown).toHaveLength(1);
    expect(shown[0].message).toBe('INV-121（MD-06）：お会計が済みました');
    expect(shown[0].button).toBe('領収書を印刷');
    expect(shown[0].id).toBe('receipt-INV-121');
    expect(print).not.toHaveBeenCalled();
  });

  it('names only the invoice when there is no table (a take-away)', () => {
    expect(run(vi.fn(async () => undefined), null).shown[0].message).toBe('INV-121：お会計が済みました');
  });

  it('prints once when the button is pressed, and says nothing when it worked', async () => {
    const print = vi.fn(async () => undefined);
    const { shown, failures } = run(print);
    shown[0].press();
    await settle();
    expect(print).toHaveBeenCalledTimes(1);
    expect(failures).toEqual([]);
  });

  it('a second press while it is printing does not print twice', async () => {
    let release: () => void = () => undefined;
    const print = vi.fn(() => new Promise<void>((resolve) => (release = resolve)));
    const { shown } = run(print);
    shown[0].press();
    shown[0].press();
    release();
    await settle();
    expect(print).toHaveBeenCalledTimes(1);
  });

  it('a failure is a message with the table and the reason, with an id of the invoice so that it does not pile up', async () => {
    const { shown, failures } = run(vi.fn(async () => {
      throw new Error('用紙がありません');
    }));
    shown[0].press();
    await settle();
    expect(failures).toEqual([{ message: 'MD-06：領収書を印刷できませんでした：用紙がありません', id: 'receipt-INV-121' }]);
  });

  it('a failure names the invoice when there is no table', async () => {
    const { shown, failures } = run(vi.fn(async () => {
      throw new Error('x');
    }), null);
    shown[0].press();
    await settle();
    expect(failures[0].message).toBe('INV-121：領収書を印刷できませんでした：x');
  });

  it('never throws out of the payment: a message that cannot be shown does not undo or hold it', () => {
    expect(() =>
      offerReceipt({
        invoice: 'INV-1',
        table: null,
        print: async () => undefined,
        show: () => {
          throw new Error('toast broke');
        },
        notifyFailure: () => undefined,
        texts,
      })
    ).not.toThrow();
  });
});

describe('where it is wired', () => {
  const read = (path: string) => readFileSync(resolve(__dirname, path), 'utf8');

  it('the payment window offers it after a payment, next to the drawer', () => {
    const dialog = read('../components/PaymentDialog.tsx');
    expect(dialog).toContain("from '../lib/receipt-offer'");
    expect(dialog).toContain('offerReceipt');
    expect(dialog).toContain('finishPayment(');
  });

  it('the button prints through the printing of an invoice (the one of the 「伝票」 screen) and never touches the drawer', () => {
    const dialog = read('../components/PaymentDialog.tsx');
    expect(dialog).toContain("from '../lib/print'");
    expect(dialog).toMatch(/offerReceipt\([\s\S]*printOrder\(/);
    expect(read('./receipt-offer.ts').replace(/\/\/.*$/gm, '')).not.toMatch(/drawer/i);
  });

  it('the invoice list gives the window the print format of the invoice (a merged bill has its own)', () => {
    expect(read('../pages/Orders.tsx')).toContain('receiptFormat=');
  });
});

describe('the words, in the four languages', () => {
  const locales = { ja, en, zh, ko } as unknown as Record<string, any>;
  it('are all there', () => {
    for (const [name, locale] of Object.entries(locales)) {
      expect(locale.payment?.receipt_offer, `${name}.payment.receipt_offer`).toBeTruthy();
      expect(locale.payment?.receipt_button, `${name}.payment.receipt_button`).toBeTruthy();
      expect(locale.errors?.receipt_failed, `${name}.errors.receipt_failed`).toBeTruthy();
    }
  });

  it('the Japanese ones are the words the shop asked for', () => {
    expect(locales.ja.payment.receipt_button).toBe('領収書を印刷');
    expect(locales.ja.payment.receipt_offer).toContain('お会計が済みました');
  });
});
