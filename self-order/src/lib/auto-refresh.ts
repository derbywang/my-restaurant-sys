// The order on the page shows what the table has ordered, and the table may be ordered for from other phones
// (and by the staff). So the page asks again when it comes back to the front, and about every 30 seconds while it
// is in front. A page that is hidden (a phone in a pocket) asks nothing.

export const REFRESH_INTERVAL_MS = 30_000

/** The part of `document` the refresh uses (so that a test can stand in for it). */
export interface VisibilitySource {
  hidden: boolean
  addEventListener(type: 'visibilitychange', listener: () => void): void
  removeEventListener(type: 'visibilitychange', listener: () => void): void
}

/**
 * Calls `refresh` when the page comes to the front and every REFRESH_INTERVAL_MS while it is there. A new ask is not
 * started while the one before has not finished; a failed ask does not stop the next. Returns the function that stops it.
 */
export function startAutoRefresh(refresh: () => Promise<unknown>, doc: VisibilitySource = document): () => void {
  let running = false
  const run = () => {
    if (doc.hidden || running) return
    running = true
    let asked: Promise<unknown>
    try {
      asked = Promise.resolve(refresh())
    } catch (err) {
      asked = Promise.reject(err)
    }
    asked
      .catch(() => undefined)
      .finally(() => {
        running = false
      })
  }
  const timer = setInterval(run, REFRESH_INTERVAL_MS)
  doc.addEventListener('visibilitychange', run)
  return () => {
    clearInterval(timer)
    doc.removeEventListener('visibilitychange', run)
  }
}
