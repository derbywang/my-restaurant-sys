import { describe, expect, it } from 'vitest'

import { mergeOrderLines } from './order-lines'
import type { OrderItem } from './api'

const line = (item_code: string, qty: number, comment: string | null = null, price = 550): OrderItem => ({
  item_code,
  item_name: item_code,
  qty,
  comment,
  price_incl_tax: price,
  amount_incl_tax: price * qty,
})

describe('the lines of "ご注文済みの内容"', () => {
  it('shows the same dish with the same note as one line', () => {
    const merged = mergeOrderLines([line('Sake', 2), line('Sake', 2), line('Sake', 2)])
    expect(merged).toHaveLength(1)
    expect(merged[0]).toMatchObject({ item_code: 'Sake', qty: 6, amount_incl_tax: 3300, price_incl_tax: 550 })
  })

  it('keeps a different note on its own line', () => {
    const merged = mergeOrderLines([line('Sake', 2, '冷やで'), line('Sake', 1), line('Sake', 1, '冷やで')])
    expect(merged.map((row) => [row.qty, row.comment])).toEqual([
      [3, '冷やで'],
      [1, null],
    ])
  })

  it('takes a missing note, an empty note and a note of spaces as the same', () => {
    const merged = mergeOrderLines([line('Sake', 1, null), line('Sake', 1, ''), line('Sake', 1, '  ')])
    expect(merged).toHaveLength(1)
    expect(merged[0].qty).toBe(3)
  })

  it('keeps the order of the first time each dish was ordered', () => {
    const merged = mergeOrderLines([line('Burger', 1), line('Sake', 2), line('Fries', 1), line('Sake', 2)])
    expect(merged.map((row) => row.item_code)).toEqual(['Burger', 'Sake', 'Fries'])
    expect(merged[1].qty).toBe(4)
  })

  it('does not change the lines it is given (the order and the kitchen ticket stay as they are)', () => {
    const lines = [line('Sake', 2), line('Sake', 2)]
    mergeOrderLines(lines)
    expect(lines.map((row) => row.qty)).toEqual([2, 2])
  })

  it('is empty for an empty order', () => {
    expect(mergeOrderLines([])).toEqual([])
  })
})

import { orderSignature } from './order-lines'

describe('orderSignature', () => {
  const line = (item_code: string, qty: number, comment = ''): OrderItem =>
    ({ item_code, item_name: item_code, qty, comment, price_incl_tax: 0, amount_incl_tax: 0 }) as OrderItem
  const order = (items: OrderItem[], grand_total = 1000, billed = false) => ({ invoice: 'INV-1', billed, grand_total, items })

  it('is empty without an order', () => {
    expect(orderSignature(null)).toBe('')
  })
  it('stays the same for the same order', () => {
    expect(orderSignature(order([line('A', 1)]))).toBe(orderSignature(order([line('A', 1)])))
  })
  it('changes when a dish is added, the amount, the state or the order changes', () => {
    const base = orderSignature(order([line('A', 1)]))
    expect(orderSignature(order([line('A', 2)]))).not.toBe(base)
    expect(orderSignature(order([line('A', 1), line('B', 1)]))).not.toBe(base)
    expect(orderSignature(order([line('A', 1)], 2000))).not.toBe(base)
    expect(orderSignature(order([line('A', 1)], 1000, true))).not.toBe(base)
    expect(orderSignature({ ...order([line('A', 1)]), invoice: 'INV-2' })).not.toBe(base)
  })
  it('changes when only a dish is swapped for another of the same count and amount', () => {
    expect(orderSignature(order([line('A', 1)]))).not.toBe(orderSignature(order([line('B', 1)])))
  })
})
