import { describe, expect, it } from 'vitest'
import { billSwitched } from './bill-switch'
import type { CustomerOrder } from './api'

function order(invoice: string | null, extra: Partial<CustomerOrder> = {}): CustomerOrder {
  return { invoice, items: [], grand_total: 0, billed: false, ...extra }
}

describe('billSwitched: the page now follows another part of a split bill', () => {
  it('is true when the bill the page showed is replaced by another part of the split bill', () => {
    expect(billSwitched(order('INV-1', { billed: true, split: true }), order('INV-2', { split: true }))).toBe(true)
  })

  it('is false for the first order a page gets', () => {
    expect(billSwitched(null, order('INV-2', { split: true }))).toBe(false)
    expect(billSwitched(order(null), order('INV-2', { split: true }))).toBe(false)
  })

  it('is false while the page stays on the same bill', () => {
    expect(billSwitched(order('INV-1', { split: true }), order('INV-1', { split: true }))).toBe(false)
  })

  it('is false when the bill was not split (the order ended, nothing to follow)', () => {
    expect(billSwitched(order('INV-1'), order('INV-2'))).toBe(false)
    expect(billSwitched(order('INV-1', { split: true }), order(null))).toBe(false)
  })
})
