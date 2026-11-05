import { describe, expect, it } from 'vitest'

import { classifyFailure, isOrderingOver } from './failure'

/** What the Frappe client throws for a refusal with a title: the titles are in `_server_messages`. */
const refusal = (title: string, httpStatus = 417) => ({
  httpStatus,
  message: 'There was an error.',
  exc_type: 'ValidationError',
  _server_messages: JSON.stringify([JSON.stringify({ message: 'Some English text', title, indicator: 'red' })]),
})

describe('what went wrong, from the error of a call', () => {
  it('knows the reasons the ordering is over, by the title the server gives', () => {
    expect(classifyFailure(refusal('Table closed'))).toBe('table_closed')
    expect(classifyFailure(refusal('Store closed'))).toBe('store_closed')
    expect(classifyFailure(refusal('Order closed'))).toBe('order_closed')
    expect(classifyFailure(refusal('Session expired', 403))).toBe('session_expired')
  })

  it('reads the title when the messages are on the response', () => {
    const err = { response: refusal('Table closed') }
    expect(classifyFailure(err)).toBe('table_closed')
  })

  it('is the age question when the server asks for it', () => {
    expect(classifyFailure(refusal('Age confirmation required'))).toBe('age')
  })

  it('is a network problem when there was no answer at all', () => {
    expect(classifyFailure({ httpStatus: 0, message: 'Network Error', exception: '' })).toBe('network')
    expect(classifyFailure(new TypeError('Failed to fetch'))).toBe('network')
  })

  it('is a server problem for an error of the server', () => {
    expect(classifyFailure({ httpStatus: 500, message: 'There was an error.' })).toBe('server')
    expect(classifyFailure({ httpStatus: 502, message: 'Bad Gateway' })).toBe('server')
  })

  it('is "other" for anything else, also a refusal with a title it does not know', () => {
    expect(classifyFailure(refusal('Something else'))).toBe('other')
    expect(classifyFailure({ httpStatus: 417 })).toBe('other')
    expect(classifyFailure(null)).toBe('other')
    expect(classifyFailure('boom')).toBe('other')
  })

  it('does not take the text of a message for its title', () => {
    const err = { _server_messages: JSON.stringify([JSON.stringify({ message: 'Table closed', title: 'Message' })]) }
    expect(classifyFailure(err)).toBe('other')
  })

  it('survives messages that are not valid', () => {
    expect(classifyFailure({ _server_messages: 'not json' })).toBe('other')
    expect(classifyFailure({ _server_messages: JSON.stringify(['not json either']) })).toBe('other')
  })

  it('says which kinds mean the ordering is over (the cart goes, the notice screen comes)', () => {
    expect(isOrderingOver('table_closed')).toBe(true)
    expect(isOrderingOver('store_closed')).toBe(true)
    expect(isOrderingOver('order_closed')).toBe(true)
    expect(isOrderingOver('session_expired')).toBe(true)
    expect(isOrderingOver('network')).toBe(false)
    expect(isOrderingOver('server')).toBe(false)
    expect(isOrderingOver('other')).toBe(false)
    expect(isOrderingOver('age')).toBe(false)
  })
})
