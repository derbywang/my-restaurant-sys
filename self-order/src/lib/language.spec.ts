import { describe, expect, it } from 'vitest'

import type { MenuItem } from './api'
import type { Cart } from './cart'
import { languageFromPhone, renameCart } from './language'

describe('the language a page starts in', () => {
  const allowed = ['ja', 'zh', 'en']

  it('a phone that scanned the code starts in its own language when the profile allows it', () => {
    expect(languageFromPhone(['zh-CN', 'en'], allowed, 'ja', 'Mobile')).toBe('zh')
    expect(languageFromPhone(['en-US'], allowed, 'ja', 'Mobile')).toBe('en')
  })

  it('the first language of the phone that the profile allows is taken', () => {
    expect(languageFromPhone(['fr-FR', 'en', 'zh-CN'], allowed, 'ja', 'Mobile')).toBe('en')
  })

  it('a language that is not allowed (Korean waits for the proofreading) is not taken', () => {
    expect(languageFromPhone(['ko-KR'], allowed, 'ja', 'Mobile')).toBe('ja')
  })

  it('the exact code is tried before the language alone (a later Traditional Chinese)', () => {
    expect(languageFromPhone(['zh-TW'], ['ja', 'zh', 'zh-TW'], 'ja', 'Mobile')).toBe('zh-TW')
    expect(languageFromPhone(['zh-TW'], allowed, 'ja', 'Mobile')).toBe('zh') // not allowed: the language alone
  })

  it('a tablet or a kiosk of the shop always starts in the default language of the session', () => {
    expect(languageFromPhone(['zh-CN'], allowed, 'ja', 'Tablet')).toBe('ja')
    expect(languageFromPhone(['zh-CN'], allowed, 'ja', 'Landscape Kiosk')).toBe('ja')
    expect(languageFromPhone(['zh-CN'], allowed, 'ja', 'Portrait Kiosk')).toBe('ja')
  })

  it('nothing known about the phone: the language of the session', () => {
    expect(languageFromPhone([], allowed, 'ja', 'Mobile')).toBe('ja')
    expect(languageFromPhone(undefined, allowed, 'ja', 'Mobile')).toBe('ja')
  })
})

describe('the cart after the language changed', () => {
  const item = (code: string, name: string): MenuItem =>
    ({ item: code, item_name: name, price_incl_tax: 100, age_check: false, special_dish: 0, disabled: 0, item_image: null, course: null, course_label: null }) as MenuItem

  it('the dishes in the cart are named as the new menu names them, quantities and notes stay', () => {
    const cart: Cart = { A: { item: item('A', '寿司'), qty: 2, note: 'わさび抜き' }, B: { item: item('B', '茶'), qty: 1, note: '' } }
    const renamed = renameCart(cart, [item('A', '寿司测试'), item('B', '茶')])
    expect(renamed.A.item.item_name).toBe('寿司测试')
    expect(renamed.A.qty).toBe(2)
    expect(renamed.A.note).toBe('わさび抜き')
    expect(renamed.B.item.item_name).toBe('茶')
  })

  it('a dish that the new menu does not have stays as it was', () => {
    const cart: Cart = { A: { item: item('A', '寿司'), qty: 1, note: '' } }
    expect(renameCart(cart, [])).toEqual(cart)
  })
})
