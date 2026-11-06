import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { REFRESH_INTERVAL_MS, startAutoRefresh, type VisibilitySource } from './auto-refresh'

/** A stand-in for `document`: visible or hidden, and a way to say the page came back to the front. */
function fakeDocument(hidden = false) {
  const listeners = new Set<() => void>()
  const doc: VisibilitySource & { show(): void; hide(): void } = {
    hidden,
    addEventListener: (_type, listener) => void listeners.add(listener),
    removeEventListener: (_type, listener) => void listeners.delete(listener),
    show() {
      doc.hidden = false
      listeners.forEach((listener) => listener())
    },
    hide() {
      doc.hidden = true
      listeners.forEach((listener) => listener())
    },
  }
  return Object.assign(doc, { listenerCount: () => listeners.size })
}

describe('keeping the order on the page up to date', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('asks again about every 30 seconds while the page is in front', async () => {
    const refresh = vi.fn().mockResolvedValue(undefined)
    startAutoRefresh(refresh, fakeDocument())
    expect(REFRESH_INTERVAL_MS).toBe(30_000)
    expect(refresh).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(30_000)
    expect(refresh).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(60_000)
    expect(refresh).toHaveBeenCalledTimes(3)
  })

  it('does not ask while the page is hidden (a phone in a pocket)', async () => {
    const refresh = vi.fn().mockResolvedValue(undefined)
    startAutoRefresh(refresh, fakeDocument(true))
    await vi.advanceTimersByTimeAsync(120_000)
    expect(refresh).not.toHaveBeenCalled()
  })

  it('asks at once when the page comes back to the front', async () => {
    const doc = fakeDocument(true)
    const refresh = vi.fn().mockResolvedValue(undefined)
    startAutoRefresh(refresh, doc)
    doc.show()
    expect(refresh).toHaveBeenCalledTimes(1)
  })

  it('does not ask when the page goes to the back', () => {
    const doc = fakeDocument(false)
    const refresh = vi.fn().mockResolvedValue(undefined)
    startAutoRefresh(refresh, doc)
    doc.hide()
    expect(refresh).not.toHaveBeenCalled()
  })

  it('does not start a second ask while the first is still on its way', async () => {
    let finish: () => void = () => {}
    const refresh = vi.fn(() => new Promise<void>((resolve) => (finish = resolve)))
    const doc = fakeDocument(true)
    startAutoRefresh(refresh, doc)
    doc.show()
    doc.hide()
    doc.show()
    await vi.advanceTimersByTimeAsync(90_000)
    expect(refresh).toHaveBeenCalledTimes(1)
    finish()
    await vi.advanceTimersByTimeAsync(30_000)
    expect(refresh).toHaveBeenCalledTimes(2)
  })

  it('keeps going after an ask failed', async () => {
    const refresh = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue(undefined)
    startAutoRefresh(refresh, fakeDocument())
    await vi.advanceTimersByTimeAsync(30_000)
    await vi.advanceTimersByTimeAsync(30_000)
    expect(refresh).toHaveBeenCalledTimes(2)
  })

  it('stops completely when told to', async () => {
    const doc = fakeDocument()
    const refresh = vi.fn().mockResolvedValue(undefined)
    const stop = startAutoRefresh(refresh, doc)
    stop()
    await vi.advanceTimersByTimeAsync(120_000)
    doc.show()
    expect(refresh).not.toHaveBeenCalled()
    expect(doc.listenerCount()).toBe(0)
  })
})
