import { describe, expect, it } from 'vitest'

import { noticeReducer } from './notice'

describe('the red notice about a problem', () => {
  it('shows the text of a failure', () => {
    expect(noticeReducer(null, { type: 'fail', text: '通信できませんでした。' })).toBe('通信できませんでした。')
  })

  it('goes away by itself when the next request succeeds', () => {
    expect(noticeReducer('通信できませんでした。', { type: 'ok' })).toBeNull()
  })

  it('stays away after a success when there was nothing to show', () => {
    expect(noticeReducer(null, { type: 'ok' })).toBeNull()
  })

  it('can be closed by the guest', () => {
    expect(noticeReducer('通信できませんでした。', { type: 'dismiss' })).toBeNull()
  })

  it('is replaced by the text of a newer failure', () => {
    expect(noticeReducer('A', { type: 'fail', text: 'B' })).toBe('B')
  })
})
