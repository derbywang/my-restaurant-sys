import { describe, expect, it } from 'vitest'

import { NOTE_MAX_LENGTH, addToCart, decrementCart, setNote, toPayload, toPreviewPayload, hasAgeCheckedDish, type Cart } from './cart'
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
