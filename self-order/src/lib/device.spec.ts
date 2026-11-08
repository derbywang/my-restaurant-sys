import { describe, expect, it } from 'vitest'
import { DEVICE_ERROR_CODES, NOT_SET_DEVICE_CODE, TABLET_MARK_PARAM, UNKNOWN_DEVICE_CODE, decide, entryFor, isTableTablet, parseSetupFragment, pollDelay, screenFor, setupDoneUrl } from './device'
import { QR_TOKEN_PARAM } from './qr-link'

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

describe('entryFor: who opened the page', () => {
  const none = { hasDevice: false, search: '', hasStoredSession: false }

  it('a phone with the code of the table order page, as always', () => {
    expect(entryFor({ ...none, search: `?${QR_TOKEN_PARAM}=abc` })).toBe('customer')
  })

  it('the code wins over the tablet mark', () => {
    expect(entryFor({ ...none, search: `?${QR_TOKEN_PARAM}=abc&${TABLET_MARK_PARAM}=1` })).toBe('customer')
  })

  it('a tablet with its credential is a device', () => {
    expect(entryFor({ ...none, hasDevice: true, search: `?${TABLET_MARK_PARAM}=1` })).toBe('device')
    expect(entryFor({ ...none, hasDevice: true })).toBe('device')
  })

  it('a reload with a stored session goes on as a customer', () => {
    expect(entryFor({ ...none, hasStoredSession: true, search: `?${TABLET_MARK_PARAM}=1` })).toBe('customer')
  })

  it('no code, no credential, with the tablet mark: the tablet is not set up', () => {
    expect(entryFor({ ...none, search: `?${TABLET_MARK_PARAM}=1` })).toBe('tablet_not_set')
  })

  it('no code, no credential, no mark: a phone that lost its code (the old message)', () => {
    expect(entryFor(none)).toBe('customer')
    expect(entryFor({ ...none, search: '?foo=1' })).toBe('customer')
  })

  it('the mark means nothing with another value', () => {
    expect(entryFor({ ...none, search: `?${TABLET_MARK_PARAM}=0` })).toBe('customer')
  })

  it('the link of a QR code of the server never carries the mark', () => {
    expect(QR_TOKEN_PARAM).not.toBe(TABLET_MARK_PARAM)
  })

  it('the page after the set-up carries the mark', () => {
    expect(setupDoneUrl()).toBe(`/order/?${TABLET_MARK_PARAM}=1`)
  })
})

describe('the code of the not-set-up screen', () => {
  it('is one of the codes the staff read out', () => {
    expect(NOT_SET_DEVICE_CODE).toBe('E-DEVICE-NOT-SET')
    expect(DEVICE_ERROR_CODES).toContain(NOT_SET_DEVICE_CODE)
  })
})
