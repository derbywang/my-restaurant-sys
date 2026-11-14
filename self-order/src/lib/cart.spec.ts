import { describe, expect, it } from 'vitest'

import {
  NOTE_MAX_LENGTH,
  addToCart,
  cartCountFor,
  decrementCart,
  incrementCart,
  lineKey,
  lineTotal,
  setNote,
  toPayload,
  toPreviewPayload,
  hasAgeCheckedDish,
  type Cart,
  type CartAddon,
} from './cart'
import type { MenuItem } from './api'

const dish = (item: string, price_incl_tax = 1100): MenuItem =>
  ({ item, item_name: item, price_incl_tax, age_check: false, disabled: 0, special_dish: 0, item_image: null, course: null, course_label: null }) as MenuItem

describe('the cart', () => {
  it('adds a dish once, then counts it up', () => {
    let cart: Cart = {}
    cart = addToCart(cart, dish('寿司'))
    cart = addToCart(cart, dish('寿司'))
    expect(cart['寿司'].qty).toBe(2)
    expect(Object.keys(cart)).toEqual(['寿司'])
  })

  it('counts down and takes the dish out at the last one, with its note', () => {
    let cart = addToCart(addToCart({}, dish('寿司')), dish('寿司'))
    cart = setNote(cart, '寿司', 'わさび抜き')
    cart = decrementCart(cart, '寿司')
    expect(cart['寿司'].qty).toBe(1)
    expect(cart['寿司'].note).toBe('わさび抜き')
    cart = decrementCart(cart, '寿司')
    expect(cart).toEqual({})
  })

  it('does not forget the note when the dish is added again', () => {
    let cart = setNote(addToCart({}, dish('寿司')), '寿司', '大盛り')
    cart = addToCart(cart, dish('寿司'))
    expect(cart['寿司']).toMatchObject({ qty: 2, note: '大盛り' })
  })

  it('leaves the cart alone for a dish that is not in it', () => {
    const cart = addToCart({}, dish('寿司'))
    expect(setNote(cart, 'ビール', 'x')).toBe(cart)
    expect(decrementCart(cart, 'ビール')).toBe(cart)
  })

  it('keeps a note to the length the order can hold (the comment field of an order line is 140)', () => {
    const cart = setNote(addToCart({}, dish('寿司')), '寿司', 'あ'.repeat(300))
    expect(NOTE_MAX_LENGTH).toBe(140)
    expect(cart['寿司'].note).toHaveLength(140)
  })
})

describe('what is sent with the order', () => {
  const cart = setNote(addToCart(addToCart(addToCart({}, dish('寿司')), dish('寿司')), dish('ビール')), '寿司', '  わさび抜き  ')

  it('sends the dishes with the quantity and the note, without the blanks around it', () => {
    expect(toPayload(cart, true)).toEqual([
      { item: '寿司', qty: 2, comment: 'わさび抜き' },
      { item: 'ビール', qty: 1 },
    ])
  })

  it('sends no note when the restaurant does not take notes', () => {
    expect(toPayload(cart, false)).toEqual([
      { item: '寿司', qty: 2 },
      { item: 'ビール', qty: 1 },
    ])
  })

  it('sends no note that is only blanks', () => {
    expect(toPayload(setNote(cart, 'ビール', '   '), true)[1]).toEqual({ item: 'ビール', qty: 1 })
  })
})

describe('the cart sent to the server for its total', () => {
  it('has the dishes and how many, nothing else (the server knows the prices and the tax)', () => {
    let cart = addToCart(addToCart({}, dish('寿司')), dish('寿司'))
    cart = setNote(addToCart(cart, dish('ビール')), 'ビール', '冷えたもの')
    expect(toPreviewPayload(cart)).toEqual([
      { item: '寿司', qty: 2 },
      { item: 'ビール', qty: 1 },
    ])
  })

  it('is empty for an empty cart', () => {
    expect(toPreviewPayload({})).toEqual([])
  })
})

describe('the age check', () => {
  const beer = { ...dish('ビール', 550), age_check: true }

  it('is needed when the cart has a dish that asks the age', () => {
    expect(hasAgeCheckedDish(addToCart(addToCart({}, dish('寿司')), beer))).toBe(true)
  })

  it('is not needed for food', () => {
    expect(hasAgeCheckedDish(addToCart({}, dish('寿司')))).toBe(false)
    expect(hasAgeCheckedDish({})).toBe(false)
  })

  it('is not needed any more when the alcohol is taken out of the cart', () => {
    expect(hasAgeCheckedDish(decrementCart(addToCart({}, beer), 'ビール'))).toBe(false)
  })
})


// A line of the cart is a combination: the dish (the grade chosen), its toppings, how many, a note.
const addon = (item: string, label: string, price = 110, age_check = false): CartAddon => ({ item, item_name: `寿司・${label}`, label, price_incl_tax: price, age_check })
const BIG = addon('寿司・大盛り', '大盛り')
const ICE = addon('ビール・氷', '氷', 55, true)

describe('a line with toppings', () => {
  it('is one line for the dish and its toppings; the key of a plain dish is its code', () => {
    expect(lineKey('寿司', [])).toBe('寿司')
    expect(lineKey('寿司', [BIG])).not.toBe('寿司')
    const cart = addToCart({}, dish('寿司'), [BIG])
    expect(Object.keys(cart)).toHaveLength(1)
    expect(cart[lineKey('寿司', [BIG])]).toMatchObject({ qty: 1, addons: [BIG], card: '寿司' })
  })

  it('counts the same combination up, and another combination is another line', () => {
    let cart = addToCart({}, dish('寿司'), [BIG])
    cart = addToCart(cart, dish('寿司'), [BIG])
    cart = addToCart(cart, dish('寿司'), [])
    expect(Object.keys(cart)).toHaveLength(2)
    expect(cart[lineKey('寿司', [BIG])].qty).toBe(2)
    expect(cart['寿司'].qty).toBe(1)
  })

  it('has the same key whatever the order of the toppings', () => {
    const MISO = addon('寿司・味噌汁', '味噌汁', 165)
    expect(lineKey('寿司', [BIG, MISO])).toBe(lineKey('寿司', [MISO, BIG]))
  })

  it('takes a quantity when it is added (the quantity of the dialog)', () => {
    const cart = addToCart({}, dish('寿司'), [BIG], 3)
    expect(cart[lineKey('寿司', [BIG])].qty).toBe(3)
  })

  it('remembers which card of the grid it came from (a grade belongs to the card of its group)', () => {
    const cart = addToCart({}, dish('寿司（上）', 1815), [], 2, '寿司')
    expect(cart['寿司（上）'].card).toBe('寿司')
    expect(cartCountFor(cart, '寿司')).toBe(2)
    expect(cartCountFor(cart, 'ビール')).toBe(0)
  })

  it('counts the cart of a card over the grades and the toppings it was ordered with', () => {
    let cart = addToCart({}, dish('寿司'), [], 1, '寿司')
    cart = addToCart(cart, dish('寿司（上）', 1815), [BIG], 2, '寿司')
    expect(cartCountFor(cart, '寿司')).toBe(3)
  })

  it('counts the toppings together with the dish: one more of the line is one more of each', () => {
    let cart = addToCart({}, dish('寿司'), [BIG], 2)
    const key = lineKey('寿司', [BIG])
    cart = incrementCart(cart, key)
    expect(cart[key].qty).toBe(3)
    cart = decrementCart(decrementCart(decrementCart(cart, key), key), key)
    expect(cart).toEqual({})
  })

  it('keeps the note of the line', () => {
    const key = lineKey('寿司', [BIG])
    const cart = setNote(addToCart({}, dish('寿司'), [BIG]), key, 'わさび抜き')
    expect(cart[key].note).toBe('わさび抜き')
    expect(setNote(cart, 'ない', 'x')).toBe(cart)
  })

  it('costs the dish and the toppings, each as many as the dish (with the tax, for the dialog and the line)', () => {
    const cart = addToCart({}, dish('寿司', 1100), [BIG], 2)
    expect(lineTotal(cart[lineKey('寿司', [BIG])])).toBe((1100 + 110) * 2)
  })
})

describe('what is sent for a line with toppings', () => {
  it('is the dish and then each topping with the quantity of the dish, next to each other', () => {
    let cart: Cart = addToCart({}, dish('寿司（上）', 1815), [BIG], 2, '寿司')
    cart = addToCart(cart, dish('ビール', 550), [])
    const key = lineKey('寿司（上）', [BIG])
    cart = setNote(cart, key, ' わさび抜き ')
    expect(toPayload(cart, true)).toEqual([
      { item: '寿司（上）', qty: 2, comment: 'わさび抜き' },
      { item: '寿司・大盛り', qty: 2 },
      { item: 'ビール', qty: 1 },
    ])
  })

  it('sends no note for the toppings (the note is for the dish)', () => {
    const key = lineKey('寿司', [BIG])
    const cart = setNote(addToCart({}, dish('寿司'), [BIG]), key, 'x')
    expect(toPayload(cart, true)[1]).toEqual({ item: '寿司・大盛り', qty: 1 })
  })

  it('is the dishes and the toppings with how many for the total (the server prices them)', () => {
    const cart = addToCart({}, dish('寿司'), [BIG], 2)
    expect(toPreviewPayload(cart)).toEqual([
      { item: '寿司', qty: 2 },
      { item: '寿司・大盛り', qty: 2 },
    ])
  })
})

describe('the age check with toppings', () => {
  it('is needed when a topping asks the age (alcohol), though the dish does not', () => {
    expect(hasAgeCheckedDish(addToCart({}, dish('寿司'), [ICE]))).toBe(true)
    expect(hasAgeCheckedDish(addToCart({}, dish('寿司'), [BIG]))).toBe(false)
  })
})
