import { beforeEach, describe, expect, it, vi } from 'vitest'

import { t } from '@ury/core'
import { initI18n, setLanguage, subscribeLanguage } from '.'

describe('switching the language of the page', () => {
  beforeEach(async () => {
    vi.stubGlobal('document', { documentElement: { lang: '' } })
    await initI18n('ja')
  })

  it('the words follow the language that was set', async () => {
    expect(t('cart.title')).toBe('カート')
    await setLanguage('zh')
    expect(t('cart.title')).toBe('购物车')
    await setLanguage('ko')
    expect(t('cart.title')).toBe('장바구니')
    await setLanguage('en')
    expect(t('cart.title')).toBe('Cart')
  })

  it('what listens is told when the language changed', async () => {
    const listener = vi.fn()
    const stop = subscribeLanguage(listener)
    await setLanguage('zh')
    expect(listener).toHaveBeenCalledTimes(1)
    stop()
    await setLanguage('ja')
    expect(listener).toHaveBeenCalledTimes(1)
  })

  it('the page says which language it is in (screen readers, fonts)', async () => {
    await setLanguage('ko')
    expect(document.documentElement.lang).toBe('ko')
  })

  it('a language without a pack of its own uses the language alone (zh-TW before its pack exists is zh)', async () => {
    await setLanguage('zh-TW')
    expect(t('cart.title')).toBe('购物车')
  })

  it('a language that has no pack at all falls back to English', async () => {
    await setLanguage('xx')
    expect(t('cart.title')).toBe('Cart')
  })
})
