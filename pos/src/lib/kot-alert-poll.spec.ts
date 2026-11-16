import { describe, expect, it, vi } from 'vitest';
import { createAlertDedupe } from './kot-alert';
import { KOT_ALERT_POLL_MS, createAlertTracker, pollKotAlerts } from './kot-alert-poll';

const row = (id: string, at: number, invoice = 'INV-1') => ({ alert_id: id, at, payload: { invoice, alert_id: id } });

describe('the kitchen error reminder, second way', () => {
  it('asks every half minute', () => {
    expect(KOT_ALERT_POLL_MS).toBe(30_000);
  });

  it('shows an alert once, whichever way it came first', () => {
    const tracker = createAlertTracker();
    expect(tracker.isNew({ alert_id: 'a1' })).toBe(true); // by the socket
    expect(tracker.isNew({ alert_id: 'a1' })).toBe(false); // the same one, by asking
    expect(tracker.isNew({ alert_id: 'a2' })).toBe(true);
  });

  it('an alert without an id (an older server) is left to the old duplicate rule', () => {
    const tracker = createAlertTracker();
    expect(tracker.isNew({ invoice: 'INV-1' })).toBe(true);
    expect(tracker.isNew({ invoice: 'INV-1' })).toBe(true);
  });

  it('asks from the last alert it has seen, and shows only the new ones', async () => {
    const tracker = createAlertTracker();
    const ask = vi.fn(async (since: number) => (since === 0 ? [row('a1', 100), row('a2', 105)] : [row('a3', 120)]));
    const shown: unknown[] = [];
    await pollKotAlerts(tracker, ask, (payload) => shown.push(payload));
    await pollKotAlerts(tracker, ask, (payload) => shown.push(payload));
    expect(ask.mock.calls.map((call) => call[0])).toEqual([0, 105]);
    expect(shown.map((p) => (p as { alert_id: string }).alert_id)).toEqual(['a1', 'a2', 'a3']);
  });

  it('does not show again what the socket already showed', async () => {
    const tracker = createAlertTracker();
    tracker.isNew({ alert_id: 'a1' });
    const shown: unknown[] = [];
    await pollKotAlerts(tracker, async () => [row('a1', 100)], (payload) => shown.push(payload));
    expect(shown).toEqual([]);
  });

  it('a failed ask is not an error: the next one tries again', async () => {
    const tracker = createAlertTracker();
    const shown: unknown[] = [];
    await expect(pollKotAlerts(tracker, async () => { throw new Error('offline'); }, (p) => shown.push(p))).resolves.toBeUndefined();
    await pollKotAlerts(tracker, async () => [row('a1', 100)], (p) => shown.push(p));
    expect(shown).toHaveLength(1);
  });

  it('the first look does not replay what is older than the page', async () => {
    // the page just opened: the server may hold an hour of alerts; the register shows them once (they are real), but never twice
    const tracker = createAlertTracker();
    const shown: unknown[] = [];
    const dedupe = createAlertDedupe(3000);
    await pollKotAlerts(tracker, async () => [row('a1', 100)], (p) => dedupe(p as Record<string, unknown>) && shown.push(p));
    expect(shown).toHaveLength(1);
  });
});
