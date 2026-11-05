// The guest's cart: one line per dish, with how many and an optional note for the kitchen.
import type { MenuItem } from './api'

/** The comment field of an order line takes 140 characters; the server cuts a longer note. */
export const NOTE_MAX_LENGTH = 140

export type CartEntry = { item: MenuItem; qty: number; note: string }
export type Cart = Record<string, CartEntry>

export function addToCart(cart: Cart, item: MenuItem): Cart {
  const existing = cart[item.item]
  return { ...cart, [item.item]: { item, qty: (existing?.qty ?? 0) + 1, note: existing?.note ?? '' } }
}

export function decrementCart(cart: Cart, itemCode: string): Cart {
  const existing = cart[itemCode]
  if (!existing) return cart
  if (existing.qty <= 1) {
    const rest = { ...cart }
    delete rest[itemCode]
    return rest
  }
  return { ...cart, [itemCode]: { ...existing, qty: existing.qty - 1 } }
}

export function setNote(cart: Cart, itemCode: string, note: string): Cart {
  const existing = cart[itemCode]
  if (!existing) return cart
  return { ...cart, [itemCode]: { ...existing, note: note.slice(0, NOTE_MAX_LENGTH) } }
}

/** What `add_customer_items` takes: the dishes with their notes (only where the restaurant takes notes). */
export function toPayload(
  cart: Cart,
  notesEnabled: boolean
): { item: string; qty: number; comment?: string }[] {
  return Object.values(cart).map((entry) => {
    const note = notesEnabled ? entry.note.trim() : ''
    return note ? { item: entry.item.item, qty: entry.qty, comment: note } : { item: entry.item.item, qty: entry.qty }
  })
}

/** What `preview_customer_cart` takes to give the total with tax: the dishes and how many, the server does the rest. */
export function toPreviewPayload(cart: Cart): { item: string; qty: number }[] {
  return Object.values(cart).map((entry) => ({ item: entry.item.item, qty: entry.qty }))
}

/** The cart has a dish that asks the guest's age (alcohol): the order is sent with the guest's answer "yes". */
export function hasAgeCheckedDish(cart: Cart): boolean {
  return Object.values(cart).some((entry) => entry.item.age_check)
}
