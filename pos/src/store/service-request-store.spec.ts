import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../lib/bell', () => ({
  isBellMuted: () => false,
  setBellMuted: vi.fn(),
  ringBell: vi.fn(),
}));

import { ringBell, setBellMuted } from '../lib/bell';

import { useServiceRequestStore } from './service-request-store';

describe('tables version', () => {
  beforeEach(() => {
    useServiceRequestStore.setState({ tablesVersion: 0 });
  });

  it('goes up each time the tables have to be read again (a call, a table that was ordered at, the poll)', () => {
    const { bumpTables } = useServiceRequestStore.getState();
    bumpTables();
    bumpTables();
    expect(useServiceRequestStore.getState().tablesVersion).toBe(2);
  });
});

describe('refresh', () => {
  it('is what the listener registers, so that any screen can ask for the calls again', () => {
    let asked = 0;
    useServiceRequestStore.getState().setRefresh(() => {
      asked += 1;
    });
    useServiceRequestStore.getState().refresh();
    expect(asked).toBe(1);
  });
});

describe('toggleMuted (the speaker buttons of the top bars and of the banner are one switch)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('turning the sound on rings once (the cashier hears the volume; the click also lets the browser play sound)', () => {
    useServiceRequestStore.setState({ muted: true });
    useServiceRequestStore.getState().toggleMuted();
    expect(useServiceRequestStore.getState().muted).toBe(false);
    expect(setBellMuted).toHaveBeenCalledWith(false);
    expect(ringBell).toHaveBeenCalledTimes(1);
  });

  it('turning the sound off is silent and is remembered', () => {
    useServiceRequestStore.setState({ muted: false });
    useServiceRequestStore.getState().toggleMuted();
    expect(useServiceRequestStore.getState().muted).toBe(true);
    expect(setBellMuted).toHaveBeenCalledWith(true);
    expect(ringBell).not.toHaveBeenCalled();
  });
});
