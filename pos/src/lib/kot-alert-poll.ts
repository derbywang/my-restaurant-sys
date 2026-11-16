// The kitchen error reminder has two ways to reach the register: the socket (real time), and asking the server every
// half minute (an iPad that slept never heard the socket). Both mark the alert by its id, so it is shown once.
export const KOT_ALERT_POLL_MS = 30_000;

export interface KotAlertRow {
  alert_id: string;
  at: number;
  payload: Record<string, unknown>;
}

export function createAlertTracker() {
  const seen = new Set<string>();
  let last = 0;
  return {
    /** True the first time an alert id is met; an alert without an id is left to the caller's other rule. */
    isNew(payload: Record<string, unknown> | null | undefined): boolean {
      const id = payload?.alert_id;
      if (typeof id !== 'string' || !id) return true;
      if (seen.has(id)) return false;
      seen.add(id);
      return true;
    },
    since(): number {
      return last;
    },
    saw(at: number) {
      if (at > last) last = at;
    },
  };
}

/** One look: ask for what came after the last alert seen and show what is new. A failed ask is not an error. */
export async function pollKotAlerts(
  tracker: ReturnType<typeof createAlertTracker>,
  ask: (since: number) => Promise<KotAlertRow[]>,
  show: (payload: Record<string, unknown>) => void
): Promise<void> {
  let rows: KotAlertRow[];
  try {
    rows = await ask(tracker.since());
  } catch {
    return;
  }
  for (const row of rows) {
    tracker.saw(row.at);
    if (tracker.isNew({ alert_id: row.alert_id })) show({ ...row.payload, alert_id: row.alert_id });
  }
}
