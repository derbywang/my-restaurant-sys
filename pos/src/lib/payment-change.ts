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
