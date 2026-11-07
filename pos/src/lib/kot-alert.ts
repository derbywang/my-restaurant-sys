// What the register says when the server reports a kitchen ticket that is missing or wrong
// (channel kot_error_<branch>_<production unit>).

type Translate = (key: string, params?: Record<string, string | number>) => string;

/**
 * The line to show. A message the server wrote itself wins; dishes no kitchen makes are named; a self-order whose ticket could not be made names its table;
 * any other failed ticket names its order.
 */
export function kotAlertMessage(payload: Record<string, unknown> | null | undefined, t: Translate): string {
  const given = payload?.message ?? payload?.error;
  if (typeof given === 'string' && given) return given;
  if (payload?.kind === 'no_kitchen' && Array.isArray(payload.items) && payload.items.length > 0) {
    return t('kot_alert.no_kitchen', { items: payload.items.map(String).join(', ') });
  }
  if (payload?.kind === 'self_order') {
    return payload.table
      ? t('kot_alert.self_order_table', { table: String(payload.table) })
      : t('kot_alert.self_order');
  }
  return payload?.invoice
    ? t('kot_alert.generic_invoice', { invoice: String(payload.invoice) })
    : t('kot_alert.generic');
}

/**
 * The alert comes on the channel of every production unit of the branch, and a register listens to all of them, so the
 * same alert arrives once per unit. `seen(payload, now)` is true the first time and false for the same alert (kind,
 * order, table, dishes) again within `windowMs`.
 */
export function createAlertDedupe(windowMs: number) {
  const last = new Map<string, number>();
  return (payload: Record<string, unknown> | null | undefined, now: number = Date.now()): boolean => {
    const key = JSON.stringify([payload?.kind, payload?.invoice, payload?.table, payload?.items, payload?.message ?? payload?.error]);
    for (const [k, at] of last) if (now - at >= windowMs) last.delete(k);
    if (last.has(key)) return false;
    last.set(key, now);
    return true;
  };
}
