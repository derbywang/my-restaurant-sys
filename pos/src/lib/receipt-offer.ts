// After a payment the cashier is offered the receipt: nothing is printed until the button is pressed (docs/deploy/printer.md, 3).
// The button prints through the printing of a paid invoice (`printOrder`, the one the 「伝票」 screen uses; the payment window gives it as
// `print`), which never opens the drawer: nothing of the drawer is in this file.

export interface ReceiptOfferTexts {
  /** "INV-1（MD-06）：お会計が済みました" from "INV-1（MD-06）" */
  offer: (name: string) => string;
  button: string;
  /** "領収書を印刷できませんでした：<reason>" */
  failed: (reason: string) => string;
}

export interface ReceiptOfferOptions {
  invoice: string;
  /** The table's name as the cashier knows it ("MD-06", or "MD-06 + MD-07" for a merged bill); null for a take-away. */
  table: string | null;
  print: () => Promise<unknown>;
  /** Shows the message with the button for a few seconds; the id is the invoice's, so the same offer does not pile up. */
  show: (message: string, button: string, press: () => void, id: string) => void;
  /** Shows the message that stays (`showToast.errorStay`). */
  notifyFailure: (message: string, id: string) => void;
  texts: ReceiptOfferTexts;
}

/** Offers the receipt of a paid invoice. Never throws: the payment has gone through whatever happens here. */
export function offerReceipt({ invoice, table, print, show, notifyFailure, texts }: ReceiptOfferOptions): void {
  let printing = false;
  const press = () => {
    if (printing) return;
    printing = true;
    void Promise.resolve()
      .then(print)
      .catch((err: unknown) => {
        const reason = err instanceof Error ? err.message : String(err);
        notifyFailure(`${table || invoice}：${texts.failed(reason)}`, `receipt-${invoice}`);
      })
      .finally(() => {
        printing = false;
      });
  };
  try {
    show(texts.offer(table ? `${invoice}（${table}）` : invoice), texts.button, press, `receipt-${invoice}`);
  } catch {
    // a message that cannot be shown must not hold or undo a payment
  }
}
