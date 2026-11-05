import { describe, expect, it } from 'vitest'

import en from './locales/en.json'
import ja from './locales/ja.json'

const keys = (obj: Record<string, unknown>, prefix = ''): string[] =>
  Object.entries(obj).flatMap(([key, value]) =>
    value && typeof value === 'object' ? keys(value as Record<string, unknown>, `${prefix}${key}.`) : [`${prefix}${key}`]
  )

describe('the words of the ordering page', () => {
  it('Japanese (the store) and English (the fallback) have the same keys', () => {
    expect(keys(ja).sort()).toEqual(keys(en).sort())
  })

  it('has no empty text', () => {
    for (const locale of [ja, en]) {
      const flat = JSON.stringify(locale)
      expect(flat).not.toMatch(/:\s*""/)
    }
  })
})
