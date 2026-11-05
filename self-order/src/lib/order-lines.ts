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
