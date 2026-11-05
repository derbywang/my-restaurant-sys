import { useCallback, useEffect, useState } from 'react';
import { parseFrappeError } from '@ury/core';
import { showToast } from '@ury/ui';
import { t } from '../i18n';
import {
  NO_SELF_ORDER,
  closeSelfOrderTable,
  getSelfOrderTables,
  openSelfOrderTable,
  type SelfOrderAction,
  type SelfOrderTables,
} from '../lib/self-order-tables';

const REFRESH_MS = 30_000;

/** The tables that are open for self ordering, kept fresh (a table also closes by itself on the server). */
export function useSelfOrderTables() {
  const [state, setState] = useState<SelfOrderTables>(NO_SELF_ORDER);
  const [now, setNow] = useState(() => Date.now());
  const [busy, setBusy] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setState(await getSelfOrderTables());
    } catch {
      setState(NO_SELF_ORDER);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const reload = window.setInterval(() => void refresh(), REFRESH_MS);
    const tick = window.setInterval(() => setNow(Date.now()), REFRESH_MS);
    return () => {
      window.clearInterval(reload);
      window.clearInterval(tick);
    };
  }, [refresh]);

  const toggle = useCallback(
    async (table: string, action: SelfOrderAction) => {
      if (action !== 'start' && action !== 'stop') return;
      setBusy(table);
      try {
        if (action === 'start') await openSelfOrderTable(table);
        else await closeSelfOrderTable(table);
        showToast.success(t(action === 'start' ? 'self_order.started' : 'self_order.stopped', { table }));
      } catch (error) {
        showToast.error(parseFrappeError(error, t('self_order.failed')));
      } finally {
        setBusy(null);
        await refresh();
      }
    },
    [refresh]
  );

  return { state, now, busy, toggle };
}
