import { describe, expect, it } from 'vitest'
import { DEVICE_ERROR_CODES, UNKNOWN_DEVICE_CODE, decide, isTableTablet, parseSetupFragment, pollDelay, screenFor } from './device'

describe('parseSetupFragment', () => {
  it('reads the device and the credential of the link', () => {
    expect(parseSetupFragment('#device=tablet-01&credential=abc123')).toEqual({
      deviceId: 'tablet-01',
      credential: 'abc123',
    })
  })

  it('does not mind the order, the # or what is escaped', () => {
    expect(parseSetupFragment('credential=a%2Fb&device=t%201')).toEqual({ deviceId: 't 1', credential: 'a/b' })
  })

  it('is nothing when one of them is missing or empty', () => {
    expect(parseSetupFragment('')).toBeNull()
    expect(parseSetupFragment('#device=t')).toBeNull()
    expect(parseSetupFragment('#credential=c')).toBeNull()
    expect(parseSetupFragment('#device=&credential=c')).toBeNull()
    expect(parseSetupFragment('#device=t&credential=%20')).toBeNull()
  })
})

describe('decide', () => {
  const open = { state: 'open' as const, opening: 'o1' }

  it('starts to order when the table is open', () => {
    expect(decide({ kind: 'waiting' }, open)).toBe('start')
  })

  it('keeps ordering while the same opening lasts', () => {
    expect(decide({ kind: 'ordering', opening: 'o1' }, open)).toBe('keep')
  })

  it('starts again when the table was opened again for the next guests', () => {
    expect(decide({ kind: 'ordering', opening: 'o1' }, { state: 'open', opening: 'o2' })).toBe('restart')
  })

  it('goes back to waiting when the table or the shop closes', () => {
    expect(decide({ kind: 'ordering', opening: 'o1' }, { state: 'table_closed', opening: null })).toBe('wait')
    expect(decide({ kind: 'ordering', opening: 'o1' }, { state: 'store_closed', opening: null })).toBe('wait')
  })

  it('goes on waiting while it is closed', () => {
    expect(decide({ kind: 'waiting' }, { state: 'table_closed', opening: null })).toBe('wait')
    expect(decide({ kind: 'waiting' }, { state: 'store_closed', opening: null })).toBe('wait')
  })
})

describe('pollDelay', () => {
  it('asks often while it waits and less often while the guests order', () => {
    expect(pollDelay('waiting')).toBeLessThan(pollDelay('ordering'))
    expect(pollDelay('waiting')).toBeGreaterThanOrEqual(3000)
    expect(pollDelay('ordering')).toBeLessThanOrEqual(30000)
  })
})

describe('screenFor', () => {
  it('says what is wrong with the set-up, with the code for the staff, and not "wait"', () => {
    expect(screenFor({ state: 'not_configured', opening: null, code: 'E-DEVICE-ORDERING-OFF' })).toEqual({
      kind: 'misconfigured',
      code: 'E-DEVICE-ORDERING-OFF',
    })
  })

  it('keeps the closed table and the closed shop apart', () => {
    expect(screenFor({ state: 'table_closed', opening: null })).toEqual({ kind: 'waiting', reason: 'table_closed' })
    expect(screenFor({ state: 'store_closed', opening: null })).toEqual({ kind: 'waiting', reason: 'store_closed' })
  })

  it('has a code even when the server sent none', () => {
    expect(screenFor({ state: 'not_configured', opening: null })).toEqual({ kind: 'misconfigured', code: 'E-UNKNOWN' })
  })
})

describe('a set-up that is not right is not an opening', () => {
  it('is waited out, never started', () => {
    expect(decide({ kind: 'waiting' }, { state: 'not_configured', opening: null, code: 'E-PROFILE-OFF' })).toBe('wait')
    expect(decide({ kind: 'ordering', opening: 'o1' }, { state: 'not_configured', opening: null, code: 'E-PROFILE-OFF' })).toBe('wait')
  })
})

describe('the codes the staff read out to the administrator', () => {
  it('has one for a tablet the server does not know, like the set-up mistakes have', () => {
    expect(UNKNOWN_DEVICE_CODE).toBe('E-DEVICE-UNKNOWN')
    expect(DEVICE_ERROR_CODES).toEqual(
      expect.arrayContaining(['E-PROFILE-OFF', 'E-DEVICE-ORDERING-OFF', 'E-NO-TABLE', 'E-TABLE-BRANCH', 'E-DEVICE-UNKNOWN'])
    )
  })
})

describe('a tablet that stays at a table', () => {
  it('is told from a kiosk and from a phone by where the session came from', () => {
    expect(isTableTablet({ source: 'Table Tablet' })).toBe(true)
    expect(isTableTablet({ source: 'Kiosk' })).toBe(false)
    expect(isTableTablet({ source: 'QR Table' })).toBe(false)
    expect(isTableTablet(null)).toBe(false)
  })
})
