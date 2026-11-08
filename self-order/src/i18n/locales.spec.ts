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

describe('the notices that stop a guest from ordering', () => {
  const closed = ja.closed as Record<string, { title: string; message: string } | string>

  it('every one tells the guest to ask the staff, and none says it is an error', () => {
    for (const kind of ['table_closed', 'store_closed', 'order_closed', 'session_expired']) {
      const { title, message } = closed[kind] as { title: string; message: string }
      expect(message, kind).toContain('スタッフにお声がけください')
      expect(`${title}${message}`, kind).not.toMatch(/エラー|失敗|error/i)
    }
  })

  it('the closed table says it can be the bill (a guest whose tables were merged for paying)', () => {
    expect((closed.table_closed as { message: string }).message).toContain('お会計中')
  })
})

describe('the notice for a bill that was split (会計分割)', () => {
  it('ja says the bills are separate, and that what is ordered from here joins this bill', () => {
    expect(ja.split.title).toBe('お会計が別々になりました。')
    expect(ja.split.message).toBe(
      'この画面には、こちらのお会計分のご注文と金額を表示しています。このあとご注文いただいた商品も、こちらのお会計に加わります。',
    )
  })

  it('does not send the guest away: they can go on ordering', () => {
    expect(ja.split.message).not.toContain('スタッフにお声がけください')
    expect(en.split.message).not.toMatch(/ask (a member of )?staff/i)
  })
})
