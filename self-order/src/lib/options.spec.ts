import { describe, expect, it } from 'vitest'

import {
  cardPrice,
  carryOverAddons,
  cartAddon,
  cartMain,
  gradesOf,
  initialGrade,
  needsAgeQuestion,
  subtotal,
} from './options'
import type { Grade, MenuItem, OptionItem, ProductInfo } from './api'

const option = (item_code: string, price_incl_tax: number, label?: string, age_check = false): OptionItem => ({
  item_code,
  item_name: label ? `寿司・${label}` : item_code,
  image: null,
  price_incl_tax,
  age_check,
  ...(label ? { label } : {}),
})
const grade = (code: string, price: number, addons: OptionItem[] = []): Grade => ({ ...option(code, price), addons })
const product = (over: Partial<ProductInfo> = {}): ProductInfo => ({
  item_code: '寿司',
  item_name: '寿司',
  description: null,
  image: null,
  price_incl_tax: 1100,
  age_check: false,
  variants: [],
  addons: [],
  ...over,
})
const card = (over: Partial<MenuItem> = {}): MenuItem =>
  ({ item: '寿司', item_name: '寿司', price_incl_tax: 1100, age_check: false, special_dish: 0, disabled: 0, item_image: 'a.jpg', course: '握り', course_label: '握り', ...over }) as MenuItem

describe('the grades of a dish', () => {
  it('are the variants of the dish when it has some', () => {
    const p = product({ variants: [grade('寿司', 1100), grade('寿司（上）', 1815)] })
    expect(gradesOf(p).map((g) => g.item_code)).toEqual(['寿司', '寿司（上）'])
  })

  it('are the dish itself, with its toppings, when it has no variants', () => {
    const p = product({ addons: [option('寿司・大盛り', 110, '大盛り')] })
    const grades = gradesOf(p)
    expect(grades).toHaveLength(1)
    expect(grades[0]).toMatchObject({ item_code: '寿司', price_incl_tax: 1100 })
    expect(grades[0].addons.map((a) => a.item_code)).toEqual(['寿司・大盛り'])
  })

  it('start with the grade that was asked for (the dish whose card was touched), else the first', () => {
    const p = product({ variants: [grade('寿司', 1100), grade('寿司（上）', 1815)] })
    expect(initialGrade(p, '寿司（上）').item_code).toBe('寿司（上）')
    expect(initialGrade(p, 'ない').item_code).toBe('寿司')
  })
})

describe('the toppings that are ticked when the grade changes', () => {
  const next = [option('寿司（上）・大盛り', 165, '大盛り'), option('寿司（上）・味噌汁', 165, '味噌汁')]

  it('stay ticked when the new grade has the same topping (by its label)', () => {
    const ticked = [option('寿司・大盛り', 110, '大盛り')]
    expect(carryOverAddons(ticked, next).map((a) => a.item_code)).toEqual(['寿司（上）・大盛り'])
  })

  it('are dropped when the new grade does not have them', () => {
    expect(carryOverAddons([option('寿司・わさび', 10, 'わさび')], next)).toEqual([])
  })

  it('are none when nothing was ticked', () => {
    expect(carryOverAddons([], next)).toEqual([])
  })
})

describe('the price in the dialog', () => {
  it('is the grade and the toppings, each as many as asked, with the tax', () => {
    expect(subtotal(option('寿司', 1100), [option('a', 110, 'a'), option('b', 55, 'b')], 3)).toBe((1100 + 110 + 55) * 3)
  })

  it('is the grade alone without toppings', () => {
    expect(subtotal(option('寿司', 1100), [], 2)).toBe(2200)
  })

  it('is nothing for no quantity', () => {
    expect(subtotal(option('寿司', 1100), [], 0)).toBe(0)
  })
})

describe('the question about the age', () => {
  it('is asked when the grade or one of the toppings is alcohol', () => {
    expect(needsAgeQuestion(option('ビール', 550, undefined, true), [])).toBe(true)
    expect(needsAgeQuestion(option('寿司', 1100), [option('氷', 55, '氷', true)])).toBe(true)
  })

  it('is not asked for food', () => {
    expect(needsAgeQuestion(option('寿司', 1100), [option('大盛り', 110, '大盛り')])).toBe(false)
  })
})

describe('what goes in the cart', () => {
  it('is the grade as a dish of the cart, with the course and the image of the card', () => {
    const main = cartMain(card(), option('寿司（上）', 1815))
    expect(main).toMatchObject({ item: '寿司（上）', item_name: '寿司（上）', price_incl_tax: 1815, course: '握り', item_image: 'a.jpg' })
  })

  it('has the age flag of the grade', () => {
    expect(cartMain(card(), option('ビール', 550, undefined, true)).age_check).toBe(true)
  })

  it('is a topping with its label, price and age flag', () => {
    expect(cartAddon(option('寿司・大盛り', 110, '大盛り'))).toEqual({
      item: '寿司・大盛り',
      item_name: '寿司・大盛り',
      label: '大盛り',
      price_incl_tax: 110,
      age_check: false,
    })
  })

  it('uses the name when a topping has no label', () => {
    expect(cartAddon(option('寿司・大盛り', 110)).label).toBe('寿司・大盛り')
  })
})

describe('the price on a card', () => {
  it('is the price, with a 〜 when the group has other prices', () => {
    expect(cardPrice(card({ price_from: true }))).toEqual({ amount: 1100, from: true })
    expect(cardPrice(card())).toEqual({ amount: 1100, from: false })
  })
})
