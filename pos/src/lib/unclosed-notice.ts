/**
 * Invoices that were never closed, as the opening screen shows them (docs/design/pos-closing.md: the closing of
 * the next shift holds them too). The cashier has to confirm them before the register is opened.
 */
export interface UnclosedInvoices {
  count: number;
  total: number;
  /** 'YYYY-MM-DD' */
  oldest_date: string;
}

/** True while the screen still waits for the cashier's confirmation: the opening button stays off. */
export function acknowledgementMissing(
  unclosed: UnclosedInvoices | null | undefined,
  acknowledged: boolean
): boolean {
  return !!unclosed && unclosed.count > 0 && !acknowledged;
}
