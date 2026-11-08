import type { CustomerOrder } from './api'

/**
 * The page showed one part of a split bill and now gets another (the first part was billed, paid or cancelled, and
 * the server moved the session to the part that is still open): the guests are told where their next dishes go.
 */
export function billSwitched(previous: CustomerOrder | null, next: CustomerOrder | null): boolean {
  return Boolean(
    previous?.invoice && next?.invoice && previous.invoice !== next.invoice && next.split === true,
  )
}
