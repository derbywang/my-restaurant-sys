import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

import en from './locales/en.json'
import ja from './locales/ja.json'

function keysOf(obj: Record<string, unknown>, prefix = ''): string[] {
  return Object.entries(obj).flatMap(([k, v]) =>
    v && typeof v === 'object' ? keysOf(v as Record<string, unknown>, `${prefix}${k}.`) : [`${prefix}${k}`]
  )
}

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return sources(path)
    return /\.(ts|tsx)$/.test(name) && !/\.spec\./.test(name) ? [path] : []
  })
}

describe('translations', () => {
  it('ja and en have the same keys', () => {
    expect(keysOf(en).sort()).toEqual(keysOf(ja).sort())
  })

  it('every key used with t() exists', () => {
    const known = new Set(keysOf(ja))
    const used = new Set<string>()
    for (const file of sources(join(__dirname, '..'))) {
      for (const m of readFileSync(file, 'utf8').matchAll(/\bt\(\s*'([a-z_]+(?:\.[a-z_]+)+)'/g)) used.add(m[1])
    }
    expect([...used].filter((k) => !known.has(k))).toEqual([])
    expect(used.size).toBeGreaterThan(10)
  })

  it('no Japanese text is left empty', () => {
    expect(keysOf(ja).filter((k) => !k.split('.').reduce((o: any, p) => o?.[p], ja))).toEqual([])
  })
})
