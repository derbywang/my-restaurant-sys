// A quiet refresh of the kitchen screen: every 30 seconds the list is read again, so a ticket whose push was lost shows
// up within 30 seconds at most. Quiet = the cards the screen already holds are kept as they are (the same objects: no
// flash, an open 「確認」 / 「上菜」 overlay stays open, a card just served stays hidden), only what really changed is added
// or dropped.

/** `current` is what the screen shows, `fetched` what the server lists now (undefined: the request failed). */
export function mergeKots(current, fetched) {
  if (!Array.isArray(fetched)) return { kots: current, changed: false };
  const held = new Map(current.map((kot) => [kot.name, kot]));
  const kots = fetched.map((kot) => held.get(kot.name) || kot);
  const changed = kots.length !== current.length || kots.some((kot, index) => kot !== current[index]);
  return { kots: changed ? kots : current, changed };
}

export const REFRESH_MS = 30000;

/**
 * Runs `task` every `ms` (30 s). A run that is still going is not started twice, a failing run does not stop the timer,
 * and `isBusy()` (optional) skips a round. Returns the function that stops it.
 */
export function startPolling(task, ms = REFRESH_MS, timers = globalThis) {
  let running = false;
  const id = timers.setInterval(async () => {
    if (running || (timers.isBusy && timers.isBusy())) return;
    running = true;
    try {
      await task();
    } catch (error) {
      // the next round tries again
    } finally {
      running = false;
    }
  }, ms);
  return () => timers.clearInterval(id);
}
