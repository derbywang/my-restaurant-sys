// The language of the ordering page. The server keeps it on the session (the guest's choice, or the profile's default);
// this decides what a phone starts with and keeps the cart in step with the names of the dishes.
import type { MenuItem } from './api'
import type { Cart } from './cart'

const SHOP_DEVICES = ['Tablet', 'Landscape Kiosk', 'Portrait Kiosk']

/**
 * A guest who scanned the QR code starts in the language of the phone when the profile allows it, else in the language of
 * the session (the profile's default). The tablets and kiosks of the shop always start in the default: whoever sat there
 * before chose their own language, and the page must not guess from the device.
 */
export function languageFromPhone(
  phoneLanguages: readonly string[] | undefined,
  allowed: readonly string[],
  sessionLanguage: string,
  layout: string,
): string {
  if (SHOP_DEVICES.includes(layout)) return sessionLanguage
  for (const phone of phoneLanguages ?? []) {
    // the exact code first (zh-TW), then the language alone (zh)
    for (const code of [phone, phone.split('-')[0]]) {
      if (allowed.includes(code)) return code
    }
  }
  return sessionLanguage
}

/**
 * The cart after the menu came in another language: the dishes are named as the new menu names them. The grades and
 * the toppings have no card on the menu; their new names come from the dialog of their dish (`optionNames`, by code).
 */
export function renameCart(
  cart: Cart,
  menu: readonly MenuItem[],
  optionNames: Record<string, { item_name: string; label?: string }> = {},
): Cart {
  const byCode = new Map(menu.map((item) => [item.item, item]))
  return Object.fromEntries(
    Object.entries(cart).map(([key, entry]) => {
      const fresh = byCode.get(entry.item.item)
      const named = optionNames[entry.item.item]
      const item = fresh
        ? { ...entry.item, item_name: fresh.item_name, course_label: fresh.course_label }
        : named
          ? { ...entry.item, item_name: named.item_name }
          : entry.item
      const addons = entry.addons.map((a) => {
        const found = optionNames[a.item]
        return found ? { ...a, item_name: found.item_name, label: found.label ?? found.item_name } : a
      })
      return [key, { ...entry, item, addons }]
    }),
  )
}
