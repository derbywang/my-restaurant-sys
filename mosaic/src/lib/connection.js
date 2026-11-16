/**
 * Is the register still connected to the server? (docs/deploy/printer.md, "iPad の長時間運用"). The apps ask the server
 * every 15 seconds; two failed looks in a row are an outage (one is a hiccup), the first answer after it ends it. The
 * browser's own "offline" is believed at once, "online" only after the server has answered. mosaic/src/lib/connection.js
 * is a copy of these rules for the Vue app.
 */

export const CHECK_MS = 15_000;
export const FAILS_BEFORE_OFFLINE = 2;

export function createConnectionMonitor({ check, onChange }) {
  let online = true;
  let fails = 0;

  const set = (next) => {
    if (next === online) return;
    online = next;
    onChange(next);
  };

  async function tick() {
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
export function startConnectionMonitor(monitor, win) {
  const timer = win.setInterval(() => monitor.tick(), CHECK_MS);
  const goOffline = () => monitor.browserOffline();
  const goOnline = () => monitor.browserOnline();
  win.addEventListener('offline', goOffline);
  win.addEventListener('online', goOnline);
  monitor.tick();
  return () => {
    win.clearInterval(timer);
    win.removeEventListener('offline', goOffline);
    win.removeEventListener('online', goOnline);
  };
}
