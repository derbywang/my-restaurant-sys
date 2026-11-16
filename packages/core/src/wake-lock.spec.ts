import { describe, expect, it, vi } from 'vitest';
import { createWakeLock } from './wake-lock';

function fakes(supported = true) {
  const listeners: Record<string, () => void> = {};
  const sentinels: { released: boolean; release: () => Promise<void>; addEventListener: (e: string, f: () => void) => void; fire: () => void }[] = [];
  const request = vi.fn(async () => {
    let onRelease: () => void = () => undefined;
    const sentinel = {
      released: false,
      release: async () => {
        sentinel.released = true;
      },
      addEventListener: (_: string, f: () => void) => {
        onRelease = f;
      },
      fire: () => {
        sentinel.released = true;
        onRelease();
      },
    };
    sentinels.push(sentinel);
    return sentinel;
  });
  const nav = supported ? { wakeLock: { request } } : {};
  const doc = {
    visibilityState: 'visible',
    addEventListener: (event: string, f: () => void) => {
      listeners[event] = f;
    },
    removeEventListener: (event: string) => {
      delete listeners[event];
    },
  };
  return { nav, doc, request, sentinels, listeners };
}

describe('keeping the screen awake', () => {
  it('asks for a screen lock and says it holds it', async () => {
    const { nav, doc, request } = fakes();
    const lock = createWakeLock(nav, doc);
    expect(await lock.start()).toBe('held');
    expect(request).toHaveBeenCalledWith('screen');
    expect(lock.state()).toBe('held');
  });

  it('says so when the browser cannot', async () => {
    const { nav, doc } = fakes(false);
    const lock = createWakeLock(nav, doc);
    expect(await lock.start()).toBe('unsupported');
  });

  it('a refused request is not an error: the screen just may sleep', async () => {
    const { doc } = fakes();
    const nav = { wakeLock: { request: vi.fn(async () => { throw new Error('NotAllowedError'); }) } };
    const lock = createWakeLock(nav, doc);
    expect(await lock.start()).toBe('refused');
  });

  it('takes the lock again when the page comes back (the browser drops it when the page is hidden)', async () => {
    const { nav, doc, request, sentinels, listeners } = fakes();
    const lock = createWakeLock(nav, doc);
    await lock.start();
    sentinels[0].fire(); // the browser released it
    expect(lock.state()).toBe('released');
    await listeners.visibilitychange();
    expect(request).toHaveBeenCalledTimes(2);
    expect(lock.state()).toBe('held');
  });

  it('does not ask again while it holds the lock, nor when the page is hidden', async () => {
    const { nav, doc, request, listeners } = fakes();
    const lock = createWakeLock(nav, doc);
    await lock.start();
    await listeners.visibilitychange();
    expect(request).toHaveBeenCalledTimes(1);
    doc.visibilityState = 'hidden';
    await listeners.visibilitychange();
    expect(request).toHaveBeenCalledTimes(1);
  });

  it('stop lets go and stops listening', async () => {
    const { nav, doc, sentinels, listeners } = fakes();
    const lock = createWakeLock(nav, doc);
    await lock.start();
    await lock.stop();
    expect(sentinels[0].released).toBe(true);
    expect(listeners.visibilitychange).toBeUndefined();
  });
});
