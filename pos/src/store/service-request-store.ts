import { create } from 'zustand';
import type { ServiceRequest } from '../lib/service-requests';
import { isBellMuted, setBellMuted } from '../lib/bell';

interface ServiceRequestState {
  requests: ServiceRequest[];
  /** `Date.now()` of the last tick: the waiting minutes are counted from it. */
  now: number;
  muted: boolean;
  setRequests: (requests: ServiceRequest[]) => void;
  tick: () => void;
  toggleMuted: () => void;
}

export const useServiceRequestStore = create<ServiceRequestState>((set, get) => ({
  requests: [],
  now: Date.now(),
  muted: isBellMuted(),
  setRequests: (requests) => set({ requests, now: Date.now() }),
  tick: () => set({ now: Date.now() }),
  toggleMuted: () => {
    const muted = !get().muted;
    setBellMuted(muted);
    set({ muted });
  },
}));
