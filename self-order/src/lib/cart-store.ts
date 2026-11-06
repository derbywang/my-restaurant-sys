import type { MenuItem } from './api'
import { NOTE_MAX_LENGTH, type Cart } from './cart'

// The cart of a guest who has not sent the order yet, kept for a reload of the page. It belongs to one
// session: when the table is opened again or the guest comes from another table the session is a new one,
// and a cart of the earlier guests is not shown to the next.

const KEY = 'ury_order_cart'

/** What the cart needs of the browser's storage (sessionStorage, or a stand-in in a test). */
export interface KeyValueStore {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
}

interface StoredLine {
  item: string
  qty: number
  note: string
}

/** Keeps the cart (the dishes, how many, the notes) for `session`; an empty cart is forgotten. */
export function saveCart(store: KeyValueStore, session: string, cart: Cart): void {
  try {
    const lines: StoredLine[] = Object.values(cart).map((entry) => ({
      item: entry.item.item,
      qty: entry.qty,
      note: entry.note,
    }))
    if (lines.length === 0) {
      store.removeItem(KEY)
      return
    }
    store.setItem(KEY, JSON.stringify({ session, lines }))
  } catch {
    // the browser refuses to store (private window, full): the cart is just not kept
  }
}

/**
 * The cart stored for `session`, built on the menu as it is now: the name and price come from the menu, a dish
 * that is not on it any more is left out. Another session, or anything that is not a cart, gives an empty one.
 */
export function loadCart(store: KeyValueStore, session: string, menu: MenuItem[]): Cart {
  try {
    const raw = store.getItem(KEY)
    if (!raw) return {}
    const stored = JSON.parse(raw)
    if (!stored || stored.session !== session || !Array.isArray(stored.lines)) return {}
    const byCode = new Map(menu.map((item) => [item.item, item]))
    const cart: Cart = {}
    for (const line of stored.lines as Partial<StoredLine>[]) {
      const item = line && typeof line.item === 'string' ? byCode.get(line.item) : undefined
      const qty = line && Number.isFinite(line.qty) ? Math.floor(line.qty as number) : 0
      if (!item || qty < 1) continue
      const note = typeof line.note === 'string' ? line.note.slice(0, NOTE_MAX_LENGTH) : ''
      cart[item.item] = { item, qty, note }
    }
    return cart
  } catch {
    return {}
  }
}

export function clearStoredCart(store: KeyValueStore): void {
  try {
    store.removeItem(KEY)
  } catch {
    // nothing to do
  }
}
