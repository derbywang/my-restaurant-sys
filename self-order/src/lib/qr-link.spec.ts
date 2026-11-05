import { describe, expect, it } from 'vitest'

import { QR_TOKEN_PARAM, tokenFromSearch } from './qr-link'

describe('tokenFromSearch', () => {
  it('reads the token from the link of the QR code, whose parameter the server writes (qr_link.json)', () => {
    expect(QR_TOKEN_PARAM).toBe('t')
    expect(tokenFromSearch(`?${QR_TOKEN_PARAM}=5LiJ5Y-L5a-_abc_DEF-123`)).toBe('5LiJ5Y-L5a-_abc_DEF-123')
  })

  it('reads it with other parameters around it, with or without the question mark', () => {
    expect(tokenFromSearch('?lang=ja&t=abc&x=1')).toBe('abc')
    expect(tokenFromSearch('t=abc')).toBe('abc')
  })

  it('is nothing when the link has no token (a link of another kind is not taken for one)', () => {
    for (const search of ['', '?', '?token=abc', '?T=abc', '?t=', '?x=1', '?tt=abc']) {
      expect(tokenFromSearch(search)).toBeNull()
    }
  })
})
