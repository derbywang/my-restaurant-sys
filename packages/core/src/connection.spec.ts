import { describe, expect, it, vi } from 'vitest';
import { CHECK_MS, FAILS_BEFORE_OFFLINE, createConnectionMonitor } from './connection';

const sequence = (...answers: (boolean | 'throw')[]) => {
  const queue = [...answers];
  return vi.fn(async () => {
    const next = queue.shift() ?? true;
    if (next === 'throw') throw new Error('network');
    return next;
  });
};

describe('the connection monitor', () => {
  it('looks every 15 seconds and is offline after two failures in a row', () => {
    expect(CHECK_MS).toBe(15_000);
    expect(FAILS_BEFORE_OFFLINE).toBe(2);
  });

  it('starts online and stays online while the server answers', async () => {
    const changes: boolean[] = [];
    const monitor = createConnectionMonitor({ check: sequence(true, true), onChange: (online) => changes.push(online) });
    await monitor.tick();
    await monitor.tick();
    expect(monitor.online()).toBe(true);
    expect(changes).toEqual([]);
  });

  it('one failed look is a hiccup, two are an outage', async () => {
    const changes: boolean[] = [];
    const monitor = createConnectionMonitor({ check: sequence(false, true, false, 'throw'), onChange: (online) => changes.push(online) });
    await monitor.tick(); // fail
    await monitor.tick(); // ok again: nothing was said
    expect(changes).toEqual([]);
    await monitor.tick(); // fail
    await monitor.tick(); // throw (counts as a failure)
    expect(changes).toEqual([false]);
    expect(monitor.online()).toBe(false);
  });

  it('the first answer after an outage brings it back, once', async () => {
    const changes: boolean[] = [];
    const monitor = createConnectionMonitor({ check: sequence(false, false, true, true), onChange: (online) => changes.push(online) });
    for (let i = 0; i < 4; i++) await monitor.tick();
    expect(changes).toEqual([false, true]);
  });

  it('the browser saying "offline" is believed at once; "online" asks the server', async () => {
    const changes: boolean[] = [];
    const check = sequence(true);
    const monitor = createConnectionMonitor({ check, onChange: (online) => changes.push(online) });
    monitor.browserOffline();
    expect(changes).toEqual([false]);
    await monitor.browserOnline();
    expect(check).toHaveBeenCalledTimes(1);
    expect(changes).toEqual([false, true]);
  });

  it('browserOnline with a silent server stays offline', async () => {
    const changes: boolean[] = [];
    const monitor = createConnectionMonitor({ check: sequence(false), onChange: (online) => changes.push(online) });
    monitor.browserOffline();
    await monitor.browserOnline();
    expect(monitor.online()).toBe(false);
    expect(changes).toEqual([false]);
  });
});
