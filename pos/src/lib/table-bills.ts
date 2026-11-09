// What the open bills of the branch say about its tables (2026-11-10, the same on the register and on the captain's screen):
//
//  - the state of a table is its OCCUPANCY (`URY Table.occupied`: 空席 / 使用中); printing a bill frees the table, so the
//    next guests can be seated at once and get a new order;
//  - a bill that is printed and not paid yet does not make the table "billed": it is a small mark on the card,
//    「会計待ち ¥1,655」 (several: 「会計待ち 2件 ¥3,310」);
//  - the order that is not printed (the guests who sit there now) decides who the table belongs to; with several of them the
//    oldest one does (never "the last row").
import { db } from '@ury/core';
import { DOCTYPES } from '../data/doctypes';
import { parseMergedWith } from './table-utils';

export interface BillRow {
  name: string;
  restaurant_table: string | null;
  custom_merged_tables: string | null;
  waiter: string;
  grand_total: number;
  invoice_printed: number;
  creation: string;
}

export interface CurrentOrder {
  invoiceName: string;
  waiter: string;
  grandTotal: number;
}

export interface WaitingBills {
  count: number;
  total: number;
}

export interface TableBills {
  /** The order of the guests at the table now (not printed); undefined when there is none. */
  current?: CurrentOrder;
  /** Printed bills not paid yet; null when there are none. */
  waiting: WaitingBills | null;
}

export function groupTableBills(rows: BillRow[]): Map<string, TableBills> {
  const sorted = [...rows].sort((a, b) => (a.creation === b.creation ? a.name.localeCompare(b.name) : a.creation < b.creation ? -1 : 1));
  const map = new Map<string, TableBills>();
  for (const row of sorted) {
    if (!row.restaurant_table) continue;
    const tables = [row.restaurant_table, ...parseMergedWith(row.custom_merged_tables)];
    for (const table of tables) {
      const entry = map.get(table) ?? { waiting: null };
      if (row.invoice_printed === 1) {
        const waiting = entry.waiting ?? { count: 0, total: 0 };
        entry.waiting = { count: waiting.count + 1, total: waiting.total + row.grand_total };
      } else if (!entry.current) {
        entry.current = { invoiceName: row.name, waiter: row.waiter, grandTotal: row.grand_total };
      }
      map.set(table, entry);
    }
  }
  return map;
}

type Translate = (key: string, params?: Record<string, string | number>) => string;

/** 「会計待ち ¥1,655」, or with several bills 「会計待ち 2件 ¥3,310」. */
export function waitingBillsLabel(waiting: WaitingBills, formatAmount: (amount: number) => string, t: Translate): string {
  const amount = formatAmount(waiting.total);
  return waiting.count > 1 ? t('tables.bills_waiting', { count: waiting.count, amount }) : t('tables.bill_waiting', { amount });
}

/** The open bills of the branch, grouped by table. */
export async function getTableBills(branch: string): Promise<Map<string, TableBills>> {
  const rows = (await db.getDocList(DOCTYPES.POS_INVOICE, {
    fields: ['name', 'restaurant_table', 'custom_merged_tables', 'waiter', 'rounded_total as grand_total', 'invoice_printed', 'creation'],
    filters: [
      ['branch', '=', branch],
      ['docstatus', '=', 0],
    ],
    limit: 0,
    asDict: true,
  } as unknown as Parameters<typeof db.getDocList>[1])) as BillRow[];
  return groupTableBills(rows);
}

