import { describe, expect, it } from 'vitest'

import { billAsked } from './bill-request'
import type { CustomerOrder } from './api'

const order = (over: Partial<CustomerOrder> = {}): CustomerOrder => ({
  invoice: 'INV-1',
  items: [],
  grand_total: 0,
  billed: false,
  ...over,
})

describe('billAsked', () => {
  it('is true after the guest pressed the button on this page', () => {
    expect(billAsked(order(), true)).toBe(true)
  })

  it('is true after a reload when the server says the order has an open call', () => {
    expect(billAsked(order({ bill_requested: true }), false)).toBe(true)
  })

  it('is false when nobody asked', () => {
    expect(billAsked(order(), false)).toBe(false)
    expect(billAsked(order({ bill_requested: false }), false)).toBe(false)
    expect(billAsked(null, false)).toBe(false)
  })

  it('is false once the bill is printed (the staff dealt with it)', () => {
    expect(billAsked(order({ bill_requested: true, billed: true }), true)).toBe(false)
  })
})
