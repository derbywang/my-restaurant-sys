import type { MenuItem } from './api'
import { NOTE_MAX_LENGTH, lineKey, type Cart, type CartAddon } from './cart'

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
  // a line with a grade or toppings: they are not on the menu, so what the dialog showed is kept with the line
  card?: string
  item_name?: string
  price_incl_tax?: number
  age_check?: boolean
  addons?: CartAddon[]
}

/** Keeps the cart (the dishes with their toppings, how many, the notes) for `session`; an empty cart is forgotten. */
export function saveCart(store: KeyValueStore, session: string, cart: Cart): void {
  try {
    const lines: StoredLine[] = Object.values(cart).map((entry) => ({
      item: entry.item.item,
      qty: entry.qty,
      note: entry.note,
      card: entry.card,
      item_name: entry.item.item_name,
      price_incl_tax: entry.item.price_incl_tax,
      age_check: entry.item.age_check,
      addons: entry.addons,
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

function validAddon(value: unknown): value is CartAddon {
  const a = value as CartAddon
  return Boolean(a) && typeof a.item === 'string' && typeof a.item_name === 'string' && Number.isFinite(a.price_incl_tax)
}

/**
 * The cart stored for `session`, built on the menu as it is now: the name and price of a plain dish come from the
 * menu, a dish that is not on it any more is left out. A line with a grade or toppings keeps what it was stored with
 * (they have no card on the menu) but needs the card it came from to be on the menu still. Another session, or
 * anything that is not a cart, gives an empty one.
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
      const code = line && typeof line.item === 'string' ? line.item : undefined
      const qty = line && Number.isFinite(line.qty) ? Math.floor(line.qty as number) : 0
      if (!code || qty < 1) continue
      const note = typeof line.note === 'string' ? line.note.slice(0, NOTE_MAX_LENGTH) : ''
      const card = typeof line.card === 'string' ? line.card : code
      const addons = Array.isArray(line.addons) ? line.addons : []
      if (!addons.every(validAddon)) continue
      const cardItem = byCode.get(card)
      if (!cardItem) continue
      let item = byCode.get(code)
      if (!item || card !== code || addons.length > 0) {
        // a grade, or a dish with toppings: what the dialog showed
        if (typeof line.item_name !== 'string' || !Number.isFinite(line.price_incl_tax)) {
          if (!item) continue
        } else if (!item || card !== code) {
          item = { ...cardItem, item: code, item_name: line.item_name, price_incl_tax: line.price_incl_tax as number, age_check: Boolean(line.age_check) }
        }
      }
      if (!item) continue
      const key = lineKey(code, addons)
      cart[key] = { key, item, qty, note, addons, card }
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
