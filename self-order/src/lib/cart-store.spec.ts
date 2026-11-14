import { beforeEach, describe, expect, it } from 'vitest'

import { clearStoredCart, loadCart, saveCart, type KeyValueStore } from './cart-store'
import { addToCart, lineKey, setNote, type Cart, type CartAddon } from './cart'
import type { MenuItem } from './api'

const dish = (item: string, price = 1100): MenuItem =>
  ({ item, item_name: item, price_incl_tax: price, age_check: false, disabled: 0, special_dish: 0, item_image: null, course: null, course_label: null }) as MenuItem

function memoryStore(): KeyValueStore {
  const data = new Map<string, string>()
  return {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => void data.set(key, value),
    removeItem: (key) => void data.delete(key),
  }
}

describe('the cart kept for a reload', () => {
  let store: KeyValueStore
  const menu = [dish('寿司'), dish('ビール', 550)]
  beforeEach(() => {
    store = memoryStore()
  })

  it('comes back after a reload of the same session, with the notes', () => {
    let cart: Cart = addToCart(addToCart({}, menu[0]), menu[0])
    cart = setNote(addToCart(cart, menu[1]), 'ビール', '冷えたもの')
    saveCart(store, 's1', cart)

    const restored = loadCart(store, 's1', menu)
    expect(restored['寿司'].qty).toBe(2)
    expect(restored['ビール']).toMatchObject({ qty: 1, note: '冷えたもの' })
  })

  it('is not restored for another session (the table was opened again, another table)', () => {
    saveCart(store, 's1', addToCart({}, menu[0]))
    expect(loadCart(store, 's2', menu)).toEqual({})
  })

  it('takes the dish and its price from the menu as it is now, not from what was stored', () => {
    saveCart(store, 's1', addToCart({}, dish('寿司', 999)))
    expect(loadCart(store, 's1', menu)['寿司'].item.price_incl_tax).toBe(1100)
  })

  it('leaves out a dish that is no longer on the menu', () => {
    saveCart(store, 's1', addToCart(addToCart({}, menu[0]), menu[1]))
    const restored = loadCart(store, 's1', [menu[1]])
    expect(Object.keys(restored)).toEqual(['ビール'])
  })

  it('is empty when nothing was stored or the store holds something that is not a cart', () => {
    expect(loadCart(store, 's1', menu)).toEqual({})
    store.setItem('ury_order_cart', 'not json')
    expect(loadCart(store, 's1', menu)).toEqual({})
    store.setItem('ury_order_cart', JSON.stringify({ session: 's1', lines: [{ item: '寿司', qty: -3, note: 5 }, { qty: 1 }, null] }))
    expect(loadCart(store, 's1', menu)).toEqual({})
  })

  it('forgets the cart when it is empty or cleared', () => {
    saveCart(store, 's1', addToCart({}, menu[0]))
    saveCart(store, 's1', {})
    expect(loadCart(store, 's1', menu)).toEqual({})
    saveCart(store, 's1', addToCart({}, menu[0]))
    clearStoredCart(store)
    expect(loadCart(store, 's1', menu)).toEqual({})
  })

  it('does not fail when the browser refuses to store (private window, full)', () => {
    const broken: KeyValueStore = {
      getItem: () => {
        throw new Error('denied')
      },
      setItem: () => {
        throw new Error('denied')
      },
      removeItem: () => {
        throw new Error('denied')
      },
    }
    expect(() => saveCart(broken, 's1', addToCart({}, menu[0]))).not.toThrow()
    expect(loadCart(broken, 's1', menu)).toEqual({})
    expect(() => clearStoredCart(broken)).not.toThrow()
  })
})


describe('the cart with toppings and grades kept for a reload', () => {
  const sushi = dish('寿司')
  const up = dish('寿司（上）', 1815) // a grade: it has no card on the menu
  const big: CartAddon = { item: '寿司・大盛り', item_name: '寿司・大盛り', label: '大盛り', price_incl_tax: 110, age_check: false }
  const menu = [sushi, dish('ビール', 550)]
  let store: KeyValueStore
  beforeEach(() => {
    store = memoryStore()
  })

  it('comes back with the grade, the toppings, the quantity and the note', () => {
    const key = lineKey('寿司（上）', [big])
    const cart = setNote(addToCart({}, up, [big], 2, '寿司'), key, 'わさび抜き')
    saveCart(store, 's1', cart)
    const restored = loadCart(store, 's1', menu)
    expect(restored[key]).toMatchObject({ qty: 2, note: 'わさび抜き', card: '寿司', addons: [big] })
    expect(restored[key].item).toMatchObject({ item: '寿司（上）', item_name: '寿司（上）', price_incl_tax: 1815 })
  })

  it('leaves out a line whose card is no longer on the menu', () => {
    saveCart(store, 's1', addToCart({}, up, [big], 1, '寿司'))
    expect(loadCart(store, 's1', [menu[1]])).toEqual({})
  })

  it('keeps the plain dishes of the old kind of store (no toppings, no card)', () => {
    store.setItem('ury_order_cart', JSON.stringify({ session: 's1', lines: [{ item: '寿司', qty: 2, note: '' }] }))
    expect(loadCart(store, 's1', menu)['寿司']).toMatchObject({ qty: 2, addons: [], card: '寿司' })
  })

  it('drops a line with toppings that are not what they should be', () => {
    store.setItem(
      'ury_order_cart',
      JSON.stringify({ session: 's1', lines: [{ item: '寿司（上）', item_name: 'x', price_incl_tax: 1, card: '寿司', qty: 1, note: '', addons: [{ nope: 1 }] }] }),
    )
    expect(loadCart(store, 's1', menu)).toEqual({})
  })
})
