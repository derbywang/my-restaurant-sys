/**
 * Is the register still connected to the server? (docs/deploy/printer.md, "iPad の長時間運用"). The apps ask the server
 * every 15 seconds; two failed looks in a row are an outage (one is a hiccup), the first answer after it ends it. The
 * browser's own "offline" is believed at once, "online" only after the server has answered. mosaic/src/lib/connection.js
 * is a copy of these rules for the Vue app.
 */

export const CHECK_MS = 15_000;
export const FAILS_BEFORE_OFFLINE = 2;

export interface ConnectionMonitorOptions {
  /** True when the server answered (a small request that needs no login). A throw counts as no answer. */
  check: () => Promise<boolean>;
  onChange: (online: boolean) => void;
}

export function createConnectionMonitor({ check, onChange }: ConnectionMonitorOptions) {
  let online = true;
  let fails = 0;

  const set = (next: boolean) => {
    if (next === online) return;
    online = next;
    onChange(next);
  };

  async function tick(): Promise<void> {
    let answered = false;
    try {
      answered = await check();
    } catch {
      answered = false;
    }
    if (answered) {
      fails = 0;
      set(true);
    } else {
      fails += 1;
      if (fails >= FAILS_BEFORE_OFFLINE) set(false);
    }
  }

  return {
    tick,
    online: () => online,
    browserOffline() {
      fails = FAILS_BEFORE_OFFLINE;
      set(false);
    },
    browserOnline: () => tick(),
  };
}

/** Run the monitor in a page: look every 15 s, and when the browser reports the network going or coming. */
export function startConnectionMonitor(
  monitor: ReturnType<typeof createConnectionMonitor>,
  win: Pick<Window, 'addEventListener' | 'removeEventListener' | 'setInterval' | 'clearInterval'>
): () => void {
  const timer = win.setInterval(() => void monitor.tick(), CHECK_MS);
  const goOffline = () => monitor.browserOffline();
  const goOnline = () => void monitor.browserOnline();
  win.addEventListener('offline', goOffline);
  win.addEventListener('online', goOnline);
  void monitor.tick();
  return () => {
    win.clearInterval(timer);
    win.removeEventListener('offline', goOffline);
    win.removeEventListener('online', goOnline);
  };
}
