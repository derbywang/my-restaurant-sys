import { describe, expect, it } from 'vitest'

import { canResume } from './resume'
import type { OrderingContext } from './api'

const context = { session: 's1', table: 'MD-05' } as OrderingContext

describe('going on with the session after a reload', () => {
  it('uses the stored session when the page has the code the session was made from', () => {
    expect(canResume('code-a', 'code-a', context)).toBe(true)
  })

  it('starts a new session for a different code (another table)', () => {
    expect(canResume('code-b', 'code-a', context)).toBe(false)
  })

  it('starts a new session when nothing is stored', () => {
    expect(canResume('code-a', null, null)).toBe(false)
    expect(canResume('code-a', 'code-a', null)).toBe(false)
  })

  it('does not decide anything without a code in the address', () => {
    expect(canResume(null, 'code-a', context)).toBe(false)
  })
})
