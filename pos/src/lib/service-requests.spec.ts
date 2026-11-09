import { describe, expect, it } from 'vitest';

import {
  LATE_AFTER_SECONDS,
  bannerRequests,
  cardState,
  normalizeRequests,
  requestsToRingFor,
  waitedSeconds,
} from './service-requests';

const row = (over: Record<string, unknown> = {}) => ({
  name: 'SR-1',
  request_type: 'Bill',
  status: 'Open',
  table: 'T-01',
  room: 'Hall',
  invoice: 'INV-1',
  waited_seconds: 30,
  ...over,
});

const FETCHED = 1_000_000;

describe('normalizeRequests', () => {
  it('reads the answer of the server', () => {
    const [request] = normalizeRequests({ message: [row()] }, FETCHED);
    expect(request).toMatchObject({ name: 'SR-1', type: 'Bill', status: 'Open', table: 'T-01', room: 'Hall', invoice: 'INV-1' });
    expect(request.waitedAtFetch).toBe(30);
    expect(request.fetchedAt).toBe(FETCHED);
  });

  it('shows nothing when the answer is not a list', () => {
    for (const answer of [null, undefined, 'x', {}, { message: null }, { message: 'x' }]) {
      expect(normalizeRequests(answer, FETCHED)).toEqual([]);
    }
  });

  it('skips rows without a name or a table, and resolved ones', () => {
    const rows = [row({ name: '' }), row({ table: '' }), row({ status: 'Resolved' }), null, row({ name: 'SR-2' })];
    expect(normalizeRequests({ message: rows }, FETCHED).map((r) => r.name)).toEqual(['SR-2']);
  });

  it('takes an unknown status as Open (it is better to ring once too often)', () => {
    expect(normalizeRequests({ message: [row({ status: 'Whatever' })] }, FETCHED)[0].status).toBe('Open');
  });
});

describe('waitedSeconds', () => {
  const [request] = normalizeRequests({ message: [row({ waited_seconds: 100 })] }, FETCHED);

  it('counts on from the moment the list was fetched (the clock of the tablet only measures the difference)', () => {
    expect(waitedSeconds(request, FETCHED)).toBe(100);
    expect(waitedSeconds(request, FETCHED + 65_000)).toBe(165);
  });

  it('is never negative', () => {
    expect(waitedSeconds(request, FETCHED - 5_000)).toBe(100);
  });
});

describe('cardState', () => {
  const list = (over: Record<string, unknown>[]) => normalizeRequests({ message: over.map((o) => row(o)) }, FETCHED);

  it('is nothing for a table without a request', () => {
    expect(cardState(list([]), 'T-01', FETCHED)).toBeNull();
    expect(cardState(list([{ table: 'T-02' }]), 'T-01', FETCHED)).toBeNull();
  });

  it('rings (not quiet) while nobody has looked, and shows the minutes', () => {
    const state = cardState(list([{ waited_seconds: 125 }]), 'T-01', FETCHED);
    expect(state).toMatchObject({ quiet: false, minutes: 2, late: false });
  });

  it('is quiet once acknowledged, but still there with its minutes', () => {
    const state = cardState(list([{ status: 'Acknowledged', waited_seconds: 125 }]), 'T-01', FETCHED);
    expect(state).toMatchObject({ quiet: true, minutes: 2 });
  });

  it('turns red after three minutes, Open or Acknowledged alike', () => {
    for (const status of ['Open', 'Acknowledged']) {
      expect(cardState(list([{ status, waited_seconds: LATE_AFTER_SECONDS }]), 'T-01', FETCHED)?.late).toBe(false);
      expect(cardState(list([{ status, waited_seconds: LATE_AFTER_SECONDS + 1 }]), 'T-01', FETCHED)?.late).toBe(true);
    }
  });

  it('keeps counting after the acknowledgement (opening the order does not start the time again)', () => {
    const before = cardState(list([{ status: 'Open', waited_seconds: 100 }]), 'T-01', FETCHED + 100_000);
    const after = cardState(list([{ status: 'Acknowledged', waited_seconds: 100 }]), 'T-01', FETCHED + 100_000);
    expect(after?.minutes).toBe(before?.minutes);
    expect(after?.late).toBe(true);
  });

  it('is not quiet when one of two requests of the table is still open', () => {
    const state = cardState(list([{ name: 'A', status: 'Acknowledged' }, { name: 'B', status: 'Open', waited_seconds: 5 }]), 'T-01', FETCHED);
    expect(state?.quiet).toBe(false);
  });

  it('shows the longest wait of the table', () => {
    const state = cardState(list([{ name: 'A', waited_seconds: 20 }, { name: 'B', waited_seconds: 200 }]), 'T-01', FETCHED);
    expect(state?.minutes).toBe(3);
  });

  it('knows nothing of calls other than the bill yet', () => {
    expect(cardState(list([{ request_type: 'Assistance' }]), 'T-01', FETCHED)).toBeNull();
  });
});

describe('bannerRequests', () => {
  it('lists only the Open ones, the longest waiting first', () => {
    const list = normalizeRequests(
      { message: [row({ name: 'A', waited_seconds: 10 }), row({ name: 'B', status: 'Acknowledged' }), row({ name: 'C', waited_seconds: 90 })] },
      FETCHED
    );
    expect(bannerRequests(list, FETCHED).map((r) => r.name)).toEqual(['C', 'A']);
  });
});

describe('requestsToRingFor', () => {
  it('rings once for each Open request, never again for the same one', () => {
    const list = normalizeRequests({ message: [row({ name: 'A' }), row({ name: 'B', status: 'Acknowledged' }), row({ name: 'C' })] }, FETCHED);
    const heard = new Set<string>();
    expect(requestsToRingFor(list, heard).map((r) => r.name)).toEqual(['A', 'C']);
    heard.add('A');
    heard.add('C');
    expect(requestsToRingFor(list, heard)).toEqual([]);
  });

  it('does not ring for the requests that are there at the first load when told to stay quiet about them', () => {
    const list = normalizeRequests({ message: [row({ name: 'A' })] }, FETCHED);
    expect(requestsToRingFor(list, new Set(['A']))).toEqual([]);
  });
});
