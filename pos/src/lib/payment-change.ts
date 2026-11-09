/**
 * What the payment dialog shows for the money entered: the change, what is still short, and
 * whether the change is allowed. Change is only given in cash, so money over the amount due must
 * be covered by the cash handed over (the server refuses it otherwise: make_invoice).
 */
export interface PaymentRow {
  mode_of_payment: string;
  amount: number;
}

export interface PaymentCheck {
  change: number;
  short: number;
  error: 'change_not_cash' | null;
}

const EPSILON = 0.005;

/**
 * The Mode of Payment the amount is filled in for: a mode of type Cash, never one found by its
 * name (ERPNext names it 「現金」 on a Japanese site). Without the types (an old session) the
 * mode called "Cash" is used if there is one.
 */
export function defaultCashMode(modes: string[], types: Record<string, string>): string | undefined {
  if (Object.keys(types).length === 0) return modes.find((mode) => mode === 'Cash');
  return modes.find((mode) => types[mode] === 'Cash');
}

/**
 * `types` maps a Mode of Payment to its type ("Cash", "Bank", ...). When it is empty (an old
 * session that cached the modes without types) the rule is not checked here.
 */
export function checkPayments(
  payments: PaymentRow[],
  due: number,
  types: Record<string, string>
): PaymentCheck {
  const paid = payments.reduce((sum, p) => sum + p.amount, 0);
  const change = Math.max(0, paid - due);
  const short = Math.max(0, due - paid);
  if (change <= EPSILON || Object.keys(types).length === 0) {
    return { change: change <= EPSILON ? 0 : change, short: short <= EPSILON ? 0 : short, error: null };
  }
  const cash = payments
    .filter((p) => types[p.mode_of_payment] === 'Cash')
    .reduce((sum, p) => sum + p.amount, 0);
  return { change, short: 0, error: change > cash + EPSILON ? 'change_not_cash' : null };
}

/**
 * The name of a payment mode as the dialog shows it: the cash mode (type Cash) in the word of the interface (「現金」),
 * whatever it is called on the site (ERPNext names it "Cash" on a site made in English); every other mode by its own name.
 * Without the types (an old session) the name is shown as it is.
 */
export function paymentModeLabel(
  name: string,
  types: Record<string, string>,
  cashLabel: string,
  id: string = name
): string {
  return types[id] === 'Cash' ? cashLabel : name;
}
