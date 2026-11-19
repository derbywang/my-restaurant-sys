// Why a call of the ordering page failed, so the page can say it in its own words.
//
// The server gives every refusal that matters a `title` (ury/ury/api/self_ordering.py): the text of the
// error is English and for developers, the title is what the page goes by. A call that got no answer at
// all is a problem of the network; anything else is shown as a general problem, never as the raw text.

export type FailureKind =
  | 'table_closed' // the staff closed the table, or opened it again for the next guests
  | 'table_not_open' // a guest scanned a table nobody has opened (yet)
  | 'store_closed' // there is no opened shift
  | 'order_closed' // the order is paid, cancelled or its bill is printed
  | 'session_expired' // the session is not valid (any more)
  | 'age' // alcohol without the answer to the age question
  | 'busy' // the order was being changed by someone else at the same moment; try again
  | 'network' // the server could not be reached
  | 'server' // the server failed
  | 'other'

const BY_TITLE: Record<string, FailureKind> = {
  'Table closed': 'table_closed',
  'Table not open': 'table_not_open',
  'Store closed': 'store_closed',
  'Order closed': 'order_closed',
  'Session expired': 'session_expired',
  'Age confirmation required': 'age',
  'Try again': 'busy',
}

/** The titles of the messages the server sent with an error (they are in `_server_messages`, twice JSON-encoded). */
function serverTitles(err: Record<string, unknown>): string[] {
  const response = (err.response ?? {}) as Record<string, unknown>
  const raw = err._server_messages ?? response._server_messages
  if (!raw) return []
  try {
    const list: unknown[] = typeof raw === 'string' ? JSON.parse(raw) : Array.isArray(raw) ? raw : []
    const titles: string[] = []
    for (const item of list) {
      const message = typeof item === 'string' ? JSON.parse(item) : item
      if (message && typeof message.title === 'string') titles.push(message.title)
    }
    return titles
  } catch {
    return []
  }
}

export function classifyFailure(err: unknown): FailureKind {
  if (!err || typeof err !== 'object') return 'other'
  if (err instanceof TypeError) return 'network' // fetch could not connect
  const e = err as Record<string, unknown>

  for (const title of serverTitles(e)) {
    if (BY_TITLE[title]) return BY_TITLE[title]
  }
  // the Frappe client gives httpStatus 0 when there was no response at all (offline, timeout)
  const status = typeof e.httpStatus === 'number' ? e.httpStatus : undefined
  if (status === 0) return 'network'
  if (status !== undefined && status >= 500) return 'server'
  return 'other'
}

/** The ordering is over for this page: the cart is dropped and a notice takes the place of the menu. */
export function isOrderingOver(kind: FailureKind): boolean {
  return kind === 'table_closed' || kind === 'table_not_open' || kind === 'store_closed' || kind === 'order_closed' || kind === 'session_expired'
}

/**
 * The ordering is over, as the order the page asks for now and then says it (`ordering`: "open", "table_closed" or "store_closed";
 * the server answers this call after the table was closed too, so that the guest could still read the order, and it
 * refuses nothing). null while it is open, when the server does not say, and for a device (a tablet or a kiosk): the
 * waiting screen of the device is the answer there, a second one would only flash.
 */
export function orderingEndOf<T extends { ordering?: string }>(order: T | null | undefined, options: { device?: boolean } = {}): FailureKind | null {
  if (options.device) return null
  const ordering = order?.ordering
  return ordering === 'table_closed' || ordering === 'store_closed' ? ordering : null
}
