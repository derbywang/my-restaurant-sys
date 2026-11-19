// The cash drawer and the server's printer (docs/deploy/printer.md). The iPad only presses a button: the server
// sends the receipt and the drawer's pulse to the printer. Nothing here throws for the drawer's sake: a payment that
// went through stays paid, whatever the drawer does.
import { call } from '@ury/core';

type Post = (method: string, args: Record<string, unknown>) => Promise<{ message: any }>;

const defaultPost: Post = (method, args) => call.post(method, args) as Promise<{ message: any }>;

export const DRAWER_FAILED = '引き出しが開きませんでした。鍵で開けてください。';

export interface DrawerAnswer {
  ok: boolean;
  message: string;
}

export interface SettlementDrawerAnswer extends DrawerAnswer {
  opened: boolean;
}

/** The cashier's button: only for who may take the money, and only when the server prints (a QZ shop has its own way). */
export function showsDrawerButton(permissions: { settle_payment?: boolean } | null, printType: string | null | undefined): boolean {
  return Boolean(permissions?.settle_payment) && printType === 'server';
}

export async function openDrawerByHand(post: Post = defaultPost, failed: string = DRAWER_FAILED): Promise<DrawerAnswer> {
  try {
    const response = await post('ury.ury.api.receipt_print.open_drawer', {});
    return { ok: Boolean(response.message?.ok), message: response.message?.message ?? '' };
  } catch {
    return { ok: false, message: failed };
  }
}

/** After the payment: the server opens the drawer when cash came in or change goes out. Never throws. */
export async function drawerAfterPayment(
  invoice: string,
  post: Post = defaultPost,
  failed: string = DRAWER_FAILED
): Promise<SettlementDrawerAnswer> {
  try {
    const response = await post('ury.ury.api.receipt_print.drawer_for_settlement', { invoice });
    const answer = response.message ?? {};
    return { ok: Boolean(answer.ok), opened: Boolean(answer.opened), message: answer.message ?? '' };
  } catch {
    return { ok: false, opened: false, message: failed };
  }
}

/** Print through the server's printer, then let the invoice know it was printed (the table is released as before). */
export async function serverPrint(
  invoice: string,
  printFormat: string | undefined,
  post: Post = defaultPost,
  markPrinted: (invoice: string) => Promise<unknown>
): Promise<void> {
  const response = await post('ury.ury.api.receipt_print.print_bill', { invoice, print_format: printFormat });
  if (!response.message?.ok) {
    throw new Error(response.message?.message || 'Printing failed');
  }
  await markPrinted(invoice);
}

export interface FinishPaymentOptions {
  /** Opens the drawer after a payment; null when the server does not print (nothing to open). */
  openDrawer: (() => Promise<SettlementDrawerAnswer>) | null;
  /** Shows the message that stays (`showToast.errorStay`); the id is the invoice's, so the same message does not pile up. */
  notify: (message: string, id: string) => void;
  /** Closes the payment window. */
  onClosed: () => void;
  /** Offers the receipt (a message with a button for a few seconds); it never holds back the window or the drawer. */
  offerReceipt?: () => void;
  table: string | null;
  invoice: string;
}

/**
 * The payment went through: close the window AT ONCE (the cashier must not wait for the drawer; one call in eleven to the printer
 * was slow) and open the drawer in the background. A drawer that did not open is a red message that stays, with the table's name so
 * that it cannot be taken for the next order's. The payment is never undone by it.
 */
export function finishPayment({ openDrawer, notify, onClosed, offerReceipt, table, invoice }: FinishPaymentOptions): void {
  const tell = (message: string) => notify(`${table || invoice}：${message}`, `drawer-${invoice}`);
  if (openDrawer) {
    void openDrawer()
      .then((answer) => {
        if (!answer.ok && answer.message) tell(answer.message);
      })
      .catch(() => tell(DRAWER_FAILED));
  }
  onClosed();
  try {
    offerReceipt?.();
  } catch {
    // the payment stays paid, and the drawer has been asked for already
  }
}
