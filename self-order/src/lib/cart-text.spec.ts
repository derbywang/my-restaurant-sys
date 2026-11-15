import { beforeAll, describe, expect, it } from 'vitest'

import { setLanguage } from '../i18n'
import { cartCountText } from './cart-text'

describe('how many things are in the cart', () => {
  beforeAll(async () => {
    await setLanguage('en')
  })

  it('English: 1 item, 2 items', () => {
    expect(cartCountText(1)).toBe('1 item')
    expect(cartCountText(2)).toBe('2 items')
    expect(cartCountText(0)).toBe('0 items')
  })

  it('Japanese, Chinese and Korean have no plural', async () => {
    await setLanguage('ja')
    expect(cartCountText(1)).toBe('1点')
    expect(cartCountText(3)).toBe('3点')
    await setLanguage('zh')
    expect(cartCountText(1)).toBe('1件')
    await setLanguage('ko')
    expect(cartCountText(1)).toBe('1개')
  })
})
