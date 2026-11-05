import { useCallback, useEffect, useState } from 'react'
import {
  addItems,
  bootstrap,
  createPaymentRequest,
  getCurrentOrder,
  getMenu,
  getStoredContext,
  previewCart,
  requestBill,
  type CartPreview,
  type CustomerOrder,
  type MenuItem,
  type OrderingContext,
  type PaymentRequestResult,
} from '../lib/api'
import { tokenFromSearch } from '../lib/qr-link'
import {
  addToCart as addToCartLine,
  decrementCart as decrementCartLine,
  setNote,
  toPayload,
  toPreviewPayload,
  type Cart,
} from '../lib/cart'

/** The total is asked of the server this long after the last change of the cart. */
const PREVIEW_DELAY_MS = 300

// Same keys api.ts uses internally for sessionStorage persistence. api.ts
// doesn't expose a clear function (only get/store), so resetSession clears
// them directly here rather than changing api.ts's exported surface.
const SESSION_KEY = 'ury_order_session'
const CONTEXT_KEY = 'ury_order_context'

function useQueryToken(): string | null {
  return tokenFromSearch(window.location.search)
}

/**
 * Owns all the stateful ordering logic shared across layouts: token
 * bootstrap, menu/order loading, cart management, order submission, and
 * bill requests. Layout components consume this hook and are responsible
 * only for rendering.
 *
 * Pass `initialContext` when the caller has already resolved a context
 * through some other bootstrap path (e.g. device-credential bootstrap for
 * a kiosk/tablet, done once in App.tsx before a layout is chosen) — this
 * skips the QR-token/session-resume bootstrap entirely and loads menu/order
 * directly against the given context, so a device only ever bootstraps once.
 */
export function useOrderingSession(initialContext?: OrderingContext) {
  const token = useQueryToken()
  const [context, setContext] = useState<OrderingContext | null>(null)
  const [menu, setMenu] = useState<MenuItem[]>([])
  const [order, setOrder] = useState<CustomerOrder | null>(null)
  const [cart, setCart] = useState<Cart>({})
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [billRequested, setBillRequested] = useState(false)
  const [paymentRequest, setPaymentRequest] = useState<PaymentRequestResult | null>(null)
  const [payingOnline, setPayingOnline] = useState(false)
  const [cartPreview, setCartPreview] = useState<CartPreview | null>(null)

  const loadOrder = useCallback(async (session: string) => {
    const current = await getCurrentOrder(session)
    setOrder(current)
  }, [])

  const init = useCallback(async () => {
    setLoading(true)
    try {
      let ctx: OrderingContext
      if (initialContext) {
        ctx = initialContext
      } else if (token) {
        ctx = await bootstrap(token)
      } else {
        const storedContext = getStoredContext()
        if (storedContext) {
          // No fresh token in the URL (e.g. a bookmarked/refreshed page)
          // — reuse the full context saved at bootstrap time, not just
          // the session token, so capabilities/table/layout survive a
          // refresh too. The backend still rejects the session once it
          // actually expires.
          ctx = storedContext
        } else {
          setError('This link is missing an ordering code. Please rescan the QR code on your table.')
          setLoading(false)
          return
        }
      }
      setContext(ctx)
      const menuResponse = await getMenu(ctx.session)
      setMenu(menuResponse.items.filter((item) => !item.disabled))
      await loadOrder(ctx.session)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load the menu. Please rescan the QR code.')
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialContext, token])

  useEffect(() => {
    init()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /**
   * Manual "start a fresh order" action — the MVP alternative to an
   * auto-idle-reset timer (not wired up yet). Always clears the cart and
   * any in-memory order/payment/bill state, and always clears both
   * sessionStorage keys so a stale session/context can never leak into the
   * next customer.
   *
   * For device-bootstrapped sessions (kiosk/tablet — `initialContext` was
   * passed to the hook) there's a durable device credential behind the
   * context, so we can immediately re-bootstrap a fresh session via `init`
   * without sending the customer back through a QR scan.
   *
   * For QR/link-based sessions there is no device credential to re-derive
   * a session from — clearing storage here means the next `init` run finds
   * neither a token override nor a stored context, so the hook falls back
   * to its normal "missing ordering code" error state and the customer (or
   * staff) must rescan/re-open the link. That is the correct outcome, not
   * a bug: a QR session's only source of truth is the token in the URL.
   */
  const resetSession = useCallback(() => {
    sessionStorage.removeItem(SESSION_KEY)
    sessionStorage.removeItem(CONTEXT_KEY)
    setCart({})
    setOrder(null)
    setBillRequested(false)
    setPaymentRequest(null)
    setPayingOnline(false)
    setSubmitting(false)
    setError(null)
    setContext(null)
    setMenu([])
    init()
  }, [init])

  function addToCart(item: MenuItem) {
    setCart((prev) => addToCartLine(prev, item))
  }

  function decrementCart(itemCode: string) {
    setCart((prev) => decrementCartLine(prev, itemCode))
  }

  function setCartNote(itemCode: string, note: string) {
    setCart((prev) => setNote(prev, itemCode, note))
  }

  const cartItems = Object.values(cart)
  const cartCount = cartItems.reduce((sum, entry) => sum + entry.qty, 0)

  // The total with the tax is the server's: the prices are not added up here. It is asked for when the cart
  // changes (and after an order is placed), and the last answer stays on the screen until the next one comes.
  const session = context?.session
  const cartKey = JSON.stringify(toPreviewPayload(cart))
  useEffect(() => {
    if (!session) return
    if (cartKey === '[]') {
      setCartPreview(null)
      return
    }
    let current = true
    const timer = window.setTimeout(() => {
      previewCart(session, JSON.parse(cartKey))
        .then((preview) => current && setCartPreview(preview))
        .catch(() => current && setCartPreview(null))
    }, PREVIEW_DELAY_MS)
    return () => {
      current = false
      window.clearTimeout(timer)
    }
  }, [session, cartKey, order?.grand_total])
  const cartTotal = cartPreview?.rounded_total ?? null

  async function submitCart() {
    if (!context || cartItems.length === 0) return
    setSubmitting(true)
    setError(null)
    try {
      const payload = toPayload(cart, Boolean(context.capabilities.item_notes_enabled))
      const updated = await addItems(context.session, payload)
      setOrder(updated)
      setCart({})
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not place the order. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleRequestBill() {
    if (!context) return
    try {
      await requestBill(context.session)
      setBillRequested(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not request the bill. Please ask staff for help.')
    }
  }

  async function payOnline() {
    if (!context) return
    setPayingOnline(true)
    setError(null)
    try {
      const result = await createPaymentRequest(context.session)
      setPaymentRequest(result)
      if (result.payment_url) {
        window.location.href = result.payment_url
      }
    } catch (err) {
      // Includes the graceful "online payment isn't set up yet" case from
      // the backend — surfaced as a normal error message, not a crash.
      setError(err instanceof Error ? err.message : 'Could not start online payment. Please pay at the counter.')
    } finally {
      setPayingOnline(false)
    }
  }

  return {
    context,
    menu,
    order,
    cart,
    loading,
    submitting,
    error,
    billRequested,
    paymentRequest,
    payingOnline,
    addToCart,
    decrementCart,
    setCartNote,
    submitCart,
    handleRequestBill,
    payOnline,
    resetSession,
    cartItems,
    cartCount,
    cartTotal,
    cartPreview,
  }
}
