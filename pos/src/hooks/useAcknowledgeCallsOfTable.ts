import { useEffect } from 'react';
import { acknowledgeTable } from '../lib/service-requests';
import { useServiceRequestStore } from '../store/service-request-store';

/**
 * A member of staff has the order of `table` open: its Open calls for the bill become Acknowledged (quiet: no ringing, no
 * banner; the table card keeps the bell and the minutes until the bill is printed, paid or cancelled). Asks once for each call.
 */
export function useAcknowledgeCallsOfTable(table: string | null): void {
  const requests = useServiceRequestStore((state) => state.requests);
  const hasOpenCall = table ? requests.some((r) => r.table === table && r.status === 'Open') : false;

  useEffect(() => {
    if (!table || !hasOpenCall) return;
    acknowledgeTable(table)
      .catch((error) => console.warn('service requests: acknowledge failed', error))
      .finally(() => useServiceRequestStore.getState().refresh());
  }, [table, hasOpenCall]);
}
