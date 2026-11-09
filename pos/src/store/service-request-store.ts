import { create } from 'zustand';
import type { ServiceRequest } from '../lib/service-requests';
import { isBellMuted, setBellMuted } from '../lib/bell';

interface ServiceRequestState {
  requests: ServiceRequest[];
  /** `Date.now()` of the last tick: the waiting minutes are counted from it. */
  now: number;
  muted: boolean;
  /** Goes up each time the screens that show tables have to read them again (a call, a table ordered at, the poll). */
  tablesVersion: number;
  bumpTables: () => void;
  /** Asks the listener to read the calls again now (set by the listener; a screen that acknowledges a call uses it). */
  refresh: () => void;
  setRefresh: (refresh: () => void) => void;
  setRequests: (requests: ServiceRequest[]) => void;
  tick: () => void;
  toggleMuted: () => void;
}

export const useServiceRequestStore = create<ServiceRequestState>((set, get) => ({
  requests: [],
  now: Date.now(),
  muted: isBellMuted(),
  tablesVersion: 0,
  bumpTables: () => set((state) => ({ tablesVersion: state.tablesVersion + 1 })),
  refresh: () => {},
  setRefresh: (refresh) => set({ refresh }),
  setRequests: (requests) => set({ requests, now: Date.now() }),
  tick: () => set({ now: Date.now() }),
  toggleMuted: () => {
    const muted = !get().muted;
    setBellMuted(muted);
    set({ muted });
  },
}));
