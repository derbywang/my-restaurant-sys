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
