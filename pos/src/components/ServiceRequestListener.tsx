import { useCallback, useEffect, useRef } from 'react';
import { getRealtimeSocket } from '../lib/realtime';
import { acknowledgeTable, getServiceRequests, requestsToRingFor } from '../lib/service-requests';
import { ringBell } from '../lib/bell';
import { useServiceRequestStore } from '../store/service-request-store';
import { usePOSStore } from '../store/pos-store';
import { useRootStore } from '../store/root-store';

/** Polling is the backup of the push (a lost connection, a proxy that does not pass it). */
const POLL_MS = 15_000;
const EVENT = 'service_request';
/** A table was ordered at by the guests (self ordering): its card must not say 空席 any more. */
const TABLE_EVENT = 'table_updated';
/** The table lists are read again this often as well (a push can be lost). */
const TABLES_POLL_MS = 30_000;

/**
 * Keeps the 「お会計」 calls of the branch fresh for the whole POS: the push refreshes at once, the poll every 15 s, and
 * both use the same refresh, so a request is counted once. Rings once for each new Open request. Opening the order of a
 * table makes its Open calls Acknowledged (quiet; the table card keeps them until the bill is printed, paid or cancelled).
 */
const ServiceRequestListener: React.FC = () => {
  const permissions = useRootStore((state) => state.permissions);
  const canSee = Boolean(permissions?.take_orders);
  const setRequests = useServiceRequestStore((state) => state.setRequests);
  const tick = useServiceRequestStore((state) => state.tick);
  const bumpTables = useServiceRequestStore((state) => state.bumpTables);
  const setRefresh = useServiceRequestStore((state) => state.setRefresh);
  const heard = useRef<Set<string>>(new Set());

  const refresh = useCallback(async () => {
    try {
      const requests = await getServiceRequests();
      setRequests(requests);
      const fresh = requestsToRingFor(requests, heard.current);
      if (fresh.length > 0) {
        ringBell();
        fresh.forEach((request) => heard.current.add(request.name));
      }
    } catch (error) {
      // a failed poll keeps what is shown; the next one tries again
      console.warn('service requests: refresh failed', error);
    }
  }, [setRequests]);

  useEffect(() => {
    if (!canSee) return;
    setRefresh(() => void refresh());
    void refresh();
    const poll = window.setInterval(() => void refresh(), POLL_MS);
    const clock = window.setInterval(tick, 15_000);
    const tables = window.setInterval(bumpTables, TABLES_POLL_MS);
    return () => {
      window.clearInterval(poll);
      window.clearInterval(clock);
      window.clearInterval(tables);
    };
  }, [canSee, refresh, tick, bumpTables, setRefresh]);

  useEffect(() => {
    if (!canSee) return;
    let cancelled = false;
    let detach: (() => void) | null = null;
    // a call (new, seen, done) changes what the cards show, and the table of a call may have just become occupied
    const handler = () => {
      void refresh();
      bumpTables();
    };
    const tableHandler = () => bumpTables();
    getRealtimeSocket()
      .then((socket) => {
        if (cancelled) return;
        socket.on(EVENT, handler);
        socket.on(TABLE_EVENT, tableHandler);
        // after a reconnect the push of the time in between was lost: look again
        socket.on('connect', handler);
        detach = () => {
          socket.off(EVENT, handler);
          socket.off(TABLE_EVENT, tableHandler);
          socket.off('connect', handler);
        };
      })
      .catch((error) => console.warn('service requests: no realtime connection (the poll still works)', error));
    return () => {
      cancelled = true;
      detach?.();
    };
  }, [canSee, refresh, bumpTables]);

  // a member of staff opens the order of a table (from the tables, the banner or the order list)
  const selectedTable = usePOSStore((state) => state.selectedTable);
  const previousTable = useRef<string | null>(selectedTable);
  useEffect(() => {
    if (!canSee || selectedTable === previousTable.current) return;
    previousTable.current = selectedTable;
    if (!selectedTable) return;
    const open = useServiceRequestStore.getState().requests.some((r) => r.table === selectedTable && r.status === 'Open');
    if (!open) return;
    acknowledgeTable(selectedTable)
      .catch((error) => console.warn('service requests: acknowledge failed', error))
      .finally(() => void refresh());
  }, [canSee, selectedTable, refresh]);

  return null;
};

export default ServiceRequestListener;
