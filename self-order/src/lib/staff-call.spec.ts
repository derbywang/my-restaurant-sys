import { describe, expect, it } from 'vitest'

import { staffCalled } from './staff-call'

describe('staffCalled', () => {
  it('is true right after the guest pressed the button, before the server has been asked again', () => {
    expect(staffCalled(null, true)).toBe(true)
  })

  it('is true after a reload when the server says a call is still open', () => {
    expect(staffCalled({ session_status: 'Active', invoice: null, open_requests: [{ name: 'R1', request_type: 'Assistance', status: 'Open' }] }, false)).toBe(true)
    expect(staffCalled({ session_status: 'Active', invoice: 'I', open_requests: [{ name: 'R1', request_type: 'Assistance', status: 'Acknowledged' }] }, false)).toBe(true)
  })

  it('is false when the staff have answered (the server says nothing is open), whatever was pressed before', () => {
    expect(staffCalled({ session_status: 'Active', invoice: null, open_requests: [] }, true)).toBe(false)
    expect(staffCalled({ session_status: 'Active', invoice: null }, true)).toBe(false)
  })

  it('does not take a call for the bill for a call for the staff', () => {
    expect(staffCalled({ session_status: 'Active', invoice: 'I', open_requests: [{ name: 'B1', request_type: 'Bill', status: 'Open' }] }, false)).toBe(false)
  })

  it('is false when nobody called', () => {
    expect(staffCalled(null, false)).toBe(false)
  })
})
