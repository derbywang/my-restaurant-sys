import type { OrderItem } from './api'

/**
 * The lines of the order as the guest reads them: the same dish with the same note is one line ("Sake × 6"),
 * however many times it was ordered. Only what is shown changes; the order and the kitchen tickets keep
 * a line for each time the dish was ordered.
 */
export function mergeOrderLines(lines: OrderItem[]): OrderItem[] {
  const merged = new Map<string, OrderItem>()
  for (const line of lines) {
    const key = `${line.item_code}\u0000${(line.comment ?? '').trim()}`
    const existing = merged.get(key)
    if (existing) {
      existing.qty += line.qty
      existing.amount_incl_tax += line.amount_incl_tax
    } else {
      merged.set(key, { ...line })
    }
  }
  return [...merged.values()]
}

/**
 * A short text that changes when the order the page shows changes (another order, a dish added, the bill printed,
 * the amount). The total of the cart is asked for again when it changes, since the total is the cart with the order.
 */
export function orderSignature(
  order: { invoice: string | null; billed: boolean; grand_total: number; items: OrderItem[] } | null
): string {
  if (!order) return ''
  const lines = order.items.map((l) => `${l.item_code}:${l.qty}:${(l.comment ?? '').trim()}`).join('|')
  return `${order.invoice ?? ''}#${order.billed ? 'billed' : 'open'}#${order.grand_total}#${lines}`
}
