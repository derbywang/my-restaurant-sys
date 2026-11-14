// The guest's cart: one line for each combination of a dish (the grade chosen), its toppings, how many and an optional
// note for the kitchen. The toppings are as many as the dish: one more of the line is one more of each.
import type { MenuItem } from './api'

/** The comment field of an order line takes 140 characters; the server cuts a longer note. */
export const NOTE_MAX_LENGTH = 140

/** A topping in the cart: a dish of its own (named 「dish・topping」) that the server prices. */
export type CartAddon = { item: string; item_name: string; label: string; price_incl_tax: number; age_check: boolean }

export type CartEntry = {
  /** The key of the line in the cart (`lineKey`). */
  key: string
  /** The dish; for a dish with grades, the grade that was chosen. */
  item: MenuItem
  qty: number
  note: string
  addons: CartAddon[]
  /** The card of the grid the line was chosen from (a grade belongs to the card of its group). */
  card: string
}
export type Cart = Record<string, CartEntry>

/** The code of the dish for a plain line, else the dish and its toppings (in any order). */
export function lineKey(item: string, addons: readonly { item: string }[]): string {
  if (addons.length === 0) return item
  return `${item}+${addons.map((a) => a.item).sort().join('+')}`
}

/** Put `qty` of the combination in the cart (counts up the line of the same combination). */
export function addToCart(cart: Cart, item: MenuItem, addons: CartAddon[] = [], qty = 1, card: string = item.item): Cart {
  const key = lineKey(item.item, addons)
  const existing = cart[key]
  return { ...cart, [key]: { key, item, addons, card, qty: (existing?.qty ?? 0) + qty, note: existing?.note ?? '' } }
}

export function incrementCart(cart: Cart, key: string): Cart {
  const existing = cart[key]
  return existing ? { ...cart, [key]: { ...existing, qty: existing.qty + 1 } } : cart
}

export function decrementCart(cart: Cart, key: string): Cart {
  const existing = cart[key]
  if (!existing) return cart
  if (existing.qty <= 1) {
    const rest = { ...cart }
    delete rest[key]
    return rest
  }
  return { ...cart, [key]: { ...existing, qty: existing.qty - 1 } }
}

export function setNote(cart: Cart, key: string, note: string): Cart {
  const existing = cart[key]
  if (!existing) return cart
  return { ...cart, [key]: { ...existing, note: note.slice(0, NOTE_MAX_LENGTH) } }
}

/** How many of the dishes of a card are in the cart (the grades and what was ordered with them). */
export function cartCountFor(cart: Cart, card: string): number {
  return Object.values(cart).reduce((sum, entry) => (entry.card === card ? sum + entry.qty : sum), 0)
}

/** What one of the line comes to with the tax: the dish and its toppings (the server's total is the one that counts). */
export function lineUnitPrice(entry: CartEntry): number {
  return entry.item.price_incl_tax + entry.addons.reduce((sum, a) => sum + a.price_incl_tax, 0)
}

export function lineTotal(entry: CartEntry): number {
  return lineUnitPrice(entry) * entry.qty
}

/**
 * What `add_customer_items` takes: the dishes with their notes (only where the restaurant takes notes). A dish is
 * followed by its toppings, as many as the dish; the note belongs to the dish.
 */
export function toPayload(
  cart: Cart,
  notesEnabled: boolean
): { item: string; qty: number; comment?: string }[] {
  return Object.values(cart).flatMap((entry) => {
    const note = notesEnabled ? entry.note.trim() : ''
    const dish = note ? { item: entry.item.item, qty: entry.qty, comment: note } : { item: entry.item.item, qty: entry.qty }
    return [dish, ...entry.addons.map((a) => ({ item: a.item, qty: entry.qty }))]
  })
}

/** What `preview_customer_cart` takes to give the total with tax: the dishes and how many, the server does the rest. */
export function toPreviewPayload(cart: Cart): { item: string; qty: number }[] {
  return Object.values(cart).flatMap((entry) => [
    { item: entry.item.item, qty: entry.qty },
    ...entry.addons.map((a) => ({ item: a.item, qty: entry.qty })),
  ])
}

/** The cart has a dish or a topping that asks the guest's age (alcohol): the order is sent with the guest's answer "yes". */
export function hasAgeCheckedDish(cart: Cart): boolean {
  return Object.values(cart).some((entry) => entry.item.age_check || entry.addons.some((a) => a.age_check))
}
