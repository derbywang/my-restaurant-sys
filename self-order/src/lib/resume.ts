import type { OrderingContext } from './api'

/**
 * Can a page that is opened (or reloaded) with the ordering code `token` go on with the session it already
 * has? Only when the session was made from that very code: then a reload keeps the cart, the age answer and
 * the order. A different code (another table) or no stored session means a new session.
 */
export function canResume(
  token: string | null,
  storedToken: string | null,
  storedContext: OrderingContext | null,
): storedContext is OrderingContext {
  return Boolean(token && storedContext && storedToken === token)
}
