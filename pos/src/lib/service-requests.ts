// 「お会計」 calls from the guests, as the POS shows them (docs/design/self-order-design.md 3.8).
//
// A request is Open (nobody has looked: ring and banner), Acknowledged (a member of staff opened the table's order: quiet,
// but the table card keeps the bell, the word and the waiting time) or Resolved (bill printed, paid or cancelled: gone).
// The server counts the waiting time (from the moment the guest pressed the button) and sends it with the list; the POS
// only adds the time since it fetched the list, so the clock and the time zone of the tablet do not matter.
import { call } from '@ury/core';

export type RequestStatus = 'Open' | 'Acknowledged';

export interface ServiceRequest {
  name: string;
  type: 'Bill' | 'Assistance';
  status: RequestStatus;
  table: string;
  room: string;
  invoice: string;
  /** Seconds waited when the list was fetched. */
  waitedAtFetch: number;
  /** `Date.now()` of that moment. */
  fetchedAt: number;
}

/** Red after three minutes (Open or Acknowledged alike). */
export const LATE_AFTER_SECONDS = 180;

const text = (value: unknown): string => (typeof value === 'string' ? value : '');

/** The answer of `get_open_service_requests`; anything unexpected is no request. */
export function normalizeRequests(answer: unknown, fetchedAt: number): ServiceRequest[] {
  const body = (answer as { message?: unknown } | null | undefined)?.message;
  if (!Array.isArray(body)) return [];
  const requests: ServiceRequest[] = [];
  for (const row of body as Array<Record<string, unknown> | null>) {
    const name = text(row?.name);
    const table = text(row?.table);
    if (!name || !table || row?.status === 'Resolved') continue;
    const waited = Number(row?.waited_seconds);
    requests.push({
      name,
      type: row?.request_type === 'Assistance' ? 'Assistance' : 'Bill',
      status: row?.status === 'Acknowledged' ? 'Acknowledged' : 'Open',
      table,
      room: text(row?.room),
      invoice: text(row?.invoice),
      waitedAtFetch: Number.isFinite(waited) && waited > 0 ? waited : 0,
      fetchedAt,
    });
  }
  return requests;
}

export function waitedSeconds(request: ServiceRequest, now: number): number {
  return request.waitedAtFetch + Math.max(0, Math.floor((now - request.fetchedAt) / 1000));
}

export interface CardState {
  /** Acknowledged: no ringing, but the card still shows it. */
  quiet: boolean;
  minutes: number;
  late: boolean;
}

/** What the card of `table` shows for its bill call; null when there is none. One still Open makes the card not quiet. */
export function cardState(requests: ServiceRequest[], table: string, now: number): CardState | null {
  const mine = requests.filter((r) => r.table === table && r.type === 'Bill');
  if (mine.length === 0) return null;
  const seconds = Math.max(...mine.map((r) => waitedSeconds(r, now)));
  return {
    quiet: mine.every((r) => r.status === 'Acknowledged'),
    minutes: Math.floor(seconds / 60),
    late: seconds > LATE_AFTER_SECONDS,
  };
}

/** The Open bill calls (what the banner shows), the longest waiting first. */
export function bannerRequests(requests: ServiceRequest[], now: number): ServiceRequest[] {
  return requests
    .filter((r) => r.type === 'Bill' && r.status === 'Open')
    .sort((a, b) => waitedSeconds(b, now) - waitedSeconds(a, now));
}

/** The Open requests nobody has been rung for yet. */
export function requestsToRingFor(requests: ServiceRequest[], heard: Set<string>): ServiceRequest[] {
  return requests.filter((r) => r.type === 'Bill' && r.status === 'Open' && !heard.has(r.name));
}

export async function getServiceRequests(): Promise<ServiceRequest[]> {
  const answer = await call.get('ury.ury.api.service_requests.get_open_service_requests');
  return normalizeRequests(answer, Date.now());
}

/** A member of staff opened the order of `table`. */
export async function acknowledgeTable(table: string): Promise<void> {
  await call.post('ury.ury.api.service_requests.acknowledge_requests_of_table', { table });
}
