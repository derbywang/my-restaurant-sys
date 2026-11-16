/**
 * Keep the screen awake (the register's iPad and the kitchen tablet must not go dark in the middle of service).
 * `navigator.wakeLock` (Safari 16.4+): the browser lets the lock go whenever the page is hidden, so it is taken again
 * when the page comes back. A browser without it, or a refusal, is not an error: the screen then follows the device's
 * own auto-lock (docs/deploy/printer.md says to set it to Never). packages/core/src/wake-lock.ts is the original; keep the two alike.
 */

export function createWakeLock(nav, doc) {
  let state = 'idle';
  let sentinel = null;

  async function take() {
    if (!nav.wakeLock) {
      state = 'unsupported';
      return state;
    }
    try {
      sentinel = await nav.wakeLock.request('screen');
      sentinel.addEventListener('release', () => {
        state = 'released';
      });
      state = 'held';
    } catch {
      state = 'refused';
    }
    return state;
  }

  const onVisible = async () => {
    if (doc.visibilityState === 'visible' && state !== 'held' && state !== 'unsupported') await take();
  };

  return {
    async start() {
      doc.addEventListener('visibilitychange', onVisible);
      return take();
    },
    async stop() {
      doc.removeEventListener('visibilitychange', onVisible);
      if (sentinel && !sentinel.released) await sentinel.release();
      sentinel = null;
      state = 'idle';
    },
    state: () => state,
  };
}
