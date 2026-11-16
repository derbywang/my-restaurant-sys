/**
 * Keep the screen awake (the register's iPad and the kitchen tablet must not go dark in the middle of service).
 * `navigator.wakeLock` (Safari 16.4+): the browser lets the lock go whenever the page is hidden, so it is taken again
 * when the page comes back. A browser without it, or a refusal, is not an error: the screen then follows the device's
 * own auto-lock (docs/deploy/printer.md says to set it to Never). mosaic/src/lib/wake-lock.js is a copy.
 */

export type WakeLockState = 'idle' | 'held' | 'released' | 'unsupported' | 'refused';

interface Sentinel {
  released?: boolean;
  release: () => Promise<void>;
  addEventListener: (event: 'release', listener: () => void) => void;
}

interface NavigatorLike {
  wakeLock?: { request: (type: 'screen') => Promise<Sentinel> };
}

interface DocumentLike {
  visibilityState: string;
  addEventListener: (event: 'visibilitychange', listener: () => void) => void;
  removeEventListener: (event: 'visibilitychange', listener: () => void) => void;
}

export function createWakeLock(nav: NavigatorLike, doc: DocumentLike) {
  let state: WakeLockState = 'idle';
  let sentinel: Sentinel | null = null;

  async function take(): Promise<WakeLockState> {
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
    async start(): Promise<WakeLockState> {
      doc.addEventListener('visibilitychange', onVisible);
      return take();
    },
    async stop(): Promise<void> {
      doc.removeEventListener('visibilitychange', onVisible);
      if (sentinel && !sentinel.released) await sentinel.release();
      sentinel = null;
      state = 'idle';
    },
    state: () => state,
  };
}
