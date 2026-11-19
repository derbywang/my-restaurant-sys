import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import { orderingEndOf } from './failure'

// 2026-11-20: the page asks for the order every 30 seconds and never learned that the table was closed (the answer had no
// such thing; only a press on a dish, which needs the open table, showed the notice). The answer now says `ordering`.
describe('what the page does with the `ordering` of the order it asks for now and then', () => {
  it('shows nothing while the ordering is open (or the server does not say)', () => {
    expect(orderingEndOf({ ordering: 'open' })).toBeNull()
    expect(orderingEndOf({})).toBeNull()
    expect(orderingEndOf(undefined)).toBeNull()
  })

  it('shows the notice of a closed table', () => {
    expect(orderingEndOf({ ordering: 'table_closed' })).toBe('table_closed')
  })

  it('shows the notice of a closed shop', () => {
    expect(orderingEndOf({ ordering: 'store_closed' })).toBe('store_closed')
  })

  it('does not know a word it was not taught (an unknown value ends nothing)', () => {
    expect(orderingEndOf({ ordering: 'something' })).toBeNull()
  })

  it('is used by the refresh that runs while the page waits', () => {
    const hook = readFileSync(resolve(__dirname, '../hooks/useOrderingSession.ts'), 'utf8')
    const refresh = hook.slice(hook.indexOf('startAutoRefresh(async () => {'))
    expect(refresh.slice(0, 700)).toContain('orderingEndOf(')
  })
})

// the bill was asked for (the table is still open: nothing is covered) or printed / paid (the table is closed: the notice
// covers the order, as it covers the menu)
describe('a bill that was asked for, printed or paid', () => {
  it('is not covered while the table is open, whatever the order says', () => {
    expect(orderingEndOf({ ordering: 'open', billed: true, bill_requested: true })).toBeNull()
  })

  it('is covered once the table is closed (the order is still there to read, the page chooses to cover it)', () => {
    expect(orderingEndOf({ ordering: 'table_closed', billed: true, bill_requested: true })).toBe('table_closed')
    expect(orderingEndOf({ ordering: 'table_closed', billed: false, state: 'paid' })).toBe('table_closed')
  })
})

// a tablet (or a kiosk) of a device has the waiting screen of the device, which replaces the whole layout when the table
// closes; the notice of the page must not be a second answer to the same thing
describe('a device session', () => {
  it('is left to the waiting screen: no notice from the order', () => {
    expect(orderingEndOf({ ordering: 'table_closed' }, { device: true })).toBeNull()
    expect(orderingEndOf({ ordering: 'store_closed' }, { device: true })).toBeNull()
  })

  it('is told apart in the hook by the context it was given (a phone has none)', () => {
    const hook = readFileSync(resolve(__dirname, '../hooks/useOrderingSession.ts'), 'utf8')
    const refresh = hook.slice(hook.indexOf('startAutoRefresh(async () => {'))
    expect(refresh.slice(0, 700)).toMatch(/device:\s*(Boolean\()?!?!?initialContext|device:\s*initialContext/)
  })
})
