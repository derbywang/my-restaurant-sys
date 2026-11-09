import { useEffect, useState } from 'react';
import { getTableBills, type TableBills } from '../lib/table-bills';
import { useServiceRequestStore } from '../store/service-request-store';

/**
 * The open bills of the branch grouped by table (see lib/table-bills.ts), read again when the tables are (a call, a table
 * ordered at, the poll of the listener) so that 「会計待ち」 follows a print, a payment or a cancellation.
 */
export function useTableBills(branch: string | null | undefined): Map<string, TableBills> {
  const [bills, setBills] = useState<Map<string, TableBills>>(new Map());
  const tablesVersion = useServiceRequestStore((state) => state.tablesVersion);

  useEffect(() => {
    if (!branch) return;
    let cancelled = false;
    getTableBills(branch)
      .then((result) => {
        if (!cancelled) setBills(result);
      })
      .catch((error) => console.warn('table bills: could not be read', error));
    return () => {
      cancelled = true;
    };
  }, [branch, tablesVersion]);

  return bills;
}
