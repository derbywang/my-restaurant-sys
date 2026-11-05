// Self ordering at the tables: the staff open a table when the guests sit down, so that they can
// order with the QR code on it. What the POS shows comes from `get_open_tables`; the server decides
// (who may, whether the branch uses it, when a table is timed out). Nothing here knows a role name.
import { call } from '@ury/core';

export interface OpenTable {
  openedAt: string | null;
  expiresAt: string | null;
  openedBy: string | null;
}

export interface SelfOrderTables {
  /** The branch has self ordering at tables and the user takes orders. */
  enabled: boolean;
  /** The branch has an opened shift (a table cannot be opened before). */
  storeOpen: boolean;
  /** Tables the button is not offered for: the bill of their order is printed (the server refuses to open them). */
  blocked: Set<string>;
  tables: Map<string, OpenTable>;
}

export const NO_SELF_ORDER: SelfOrderTables = { enabled: false, storeOpen: false, blocked: new Set(), tables: new Map() };

const text = (value: unknown): string | null => (typeof value === 'string' && value !== '' ? value : null);

/** The answer of `get_open_tables`; anything unexpected means nothing is offered. */
export function normalizeOpenTables(answer: unknown): SelfOrderTables {
  const body = (answer as { message?: unknown } | null | undefined)?.message;
  const data = body as { enabled?: unknown; store_open?: unknown; tables?: unknown; blocked?: unknown } | null | undefined;
  if (!data || data.enabled !== true) return NO_SELF_ORDER;

  const tables = new Map<string, OpenTable>();
  if (Array.isArray(data.tables)) {
    for (const row of data.tables as Array<Record<string, unknown> | null>) {
      const name = text(row?.table);
      if (!name) continue;
      tables.set(name, {
        openedAt: text(row?.opened_at),
        expiresAt: text(row?.expires_at),
        openedBy: text(row?.opened_by),
      });
    }
  }
  const blocked = new Set<string>(
    Array.isArray(data.blocked) ? (data.blocked as unknown[]).filter((name): name is string => typeof name === 'string' && name !== '') : []
  );
  return { enabled: true, storeOpen: data.store_open === true, blocked, tables };
}

/** Whole minutes since the table was opened (never negative; 0 when the time is not usable). */
export function minutesOpen(openedAt: string | null, now: number = Date.now()): number {
  if (!openedAt) return 0;
  const opened = new Date(openedAt.replace(' ', 'T')).getTime();
  if (Number.isNaN(opened)) return 0;
  return Math.max(0, Math.floor((now - opened) / 60000));
}

export type SelfOrderAction = 'none' | 'blocked' | 'start' | 'start-disabled' | 'stop';

/** The button of a table card: nothing, a note why not (bill printed), start, start (but not now) or stop. A stop is always possible. */
export function selfOrderAction(
  state: SelfOrderTables,
  table: string,
  options: { isTakeAway: boolean }
): SelfOrderAction {
  if (!state.enabled || options.isTakeAway) return 'none';
  if (state.tables.has(table)) return 'stop';
  if (state.blocked.has(table)) return 'blocked';
  return state.storeOpen ? 'start' : 'start-disabled';
}

export async function getSelfOrderTables(): Promise<SelfOrderTables> {
  return normalizeOpenTables(await call.get('ury.ury.api.self_ordering.get_open_tables'));
}

export async function openSelfOrderTable(table: string): Promise<void> {
  await call.post('ury.ury.api.self_ordering.open_table_for_ordering', { table });
}

export async function closeSelfOrderTable(table: string): Promise<void> {
  await call.post('ury.ury.api.self_ordering.close_table_for_ordering', { table });
}
