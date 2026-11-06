import { useCallback, useEffect, useReducer, useState } from 'react'
import {
  addItems,
  bootstrap,
  createPaymentRequest,
  getCurrentOrder,
  confirmAge,
  getMenu,
  getStoredContext,
  getStoredToken,
  previewCart,
  requestBill,
  type CartPreview,
  type CustomerOrder,
  type MenuItem,
  type OrderingContext,
  type PaymentRequestResult,
} from '../lib/api'
import { tokenFromSearch } from '../lib/qr-link'
import { canResume } from '../lib/resume'
import { noticeReducer } from '../lib/notice'
import { clearStoredCart, loadCart, saveCart } from '../lib/cart-store'
import { classifyFailure, isOrderingOver, type FailureKind } from '../lib/failure'
import { t } from '../i18n'
import {
  addToCart as addToCartLine,
  decrementCart as decrementCartLine,
  hasAgeCheckedDish,
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
const TOKEN_KEY = 'ury_order_token'

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
  // The red notice: a failure shows it, the next request that succeeds (and the guest's close button) takes it away.
  const [error, dispatchNotice] = useReducer(noticeReducer, null)
  const setError = useCallback(
    (text: string | null) => dispatchNotice(text === null ? { type: 'ok' } : { type: 'fail', text }),
    [],
  )
  const dismissError = useCallback(() => dispatchNotice({ type: 'dismiss' }), [])
  // The cart is kept for a reload of the page once it has been restored (lib/cart-store.ts): saving before that
  // would overwrite the stored cart with the empty one the page starts with.
  const [cartRestored, setCartRestored] = useState(false)
  const [billRequested, setBillRequested] = useState(false)
  const [paymentRequest, setPaymentRequest] = useState<PaymentRequestResult | null>(null)
  const [payingOnline, setPayingOnline] = useState(false)
  const [cartPreview, setCartPreview] = useState<CartPreview | null>(null)
  // the server could not give the total of the cart: the page says so instead of waiting for it
  const [previewFailed, setPreviewFailed] = useState(false)
  // why the ordering is over for this page (the table was closed ...): a notice replaces the menu and the cart
  const [closed, setClosed] = useState<FailureKind | null>(null)
  // the alcohol the guest is being asked about ("20歳以上ですか？"); it is not in the cart until the answer is yes
  const [ageQuestion, setAgeQuestion] = useState<MenuItem | null>(null)
  // asked once per session: after a yes the next alcohol goes straight in (the server keeps the answer too)
  const [ageConfirmed, setAgeConfirmed] = useState(false)

  const loadOrder = useCallback(async (session: string) => {
    const current = await getCurrentOrder(session)
    setOrder(current)
  }, [])

  // What a failed call means for the page. When the ordering is over (the table was closed or opened again
  // for the next guests, the shift is closed, the order is paid, the session ran out) the cart is dropped
  // and a notice replaces the menu: nothing more can be ordered from this page. Anything else is said in
  // words of the page (no connection, a problem of the server), never in the raw text of the server.
  const handleFailure = useCallback((err: unknown) => {
    const kind = classifyFailure(err)
    if (isOrderingOver(kind)) {
      setCart({})
      setCartPreview(null)
      setPreviewFailed(false)
      setAgeQuestion(null)
      setError(null)
      setClosed(kind)
    } else {
      if (kind === 'age') setAgeConfirmed(false) // the server has no answer of this guest: ask again
      setError(t(`errors.${kind}`))
    }
    return kind
  }, [])

  const init = useCallback(async () => {
    setLoading(true)
    try {
      let ctx: OrderingContext
      // a session taken from the stored one (a reload) is tried first and replaced by a new one if the
      // server no longer accepts it (the table was opened again, the session expired)
      let resumed = false
      const stored = getStoredContext()
      if (initialContext) {
        ctx = initialContext
      } else if (token) {
        // The address keeps the code after a reload; a new session for every reload would forget the
        // age answer and the order of the guest.
        if (canResume(token, getStoredToken(), stored)) {
          ctx = stored
          resumed = true
        } else {
          ctx = await bootstrap(token)
        }
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
          setError(t('errors.no_code'))
          setLoading(false)
          return
        }
      }
      let menuResponse
      try {
        menuResponse = await getMenu(ctx.session)
      } catch (err) {
        if (!resumed || !token) throw err
        ctx = await bootstrap(token)
        menuResponse = await getMenu(ctx.session)
      }
      setContext(ctx)
      const menuItems = menuResponse.items.filter((item) => !item.disabled)
      setMenu(menuItems)
      setCart(loadCart(sessionStorage, ctx.session, menuItems))
      setCartRestored(true)
      setAgeConfirmed(Boolean(menuResponse.age_confirmed))
      await loadOrder(ctx.session)
      setError(null) // the page works: a notice of an earlier problem is over
    } catch (err) {
      handleFailure(err)
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialContext, token, handleFailure, setError])

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
    sessionStorage.removeItem(TOKEN_KEY)
    clearStoredCart(sessionStorage)
    setCartRestored(false)
    setCart({})
    setOrder(null)
    setBillRequested(false)
    setPaymentRequest(null)
    setPayingOnline(false)
    setSubmitting(false)
    setError(null)
    setAgeConfirmed(false)
    setClosed(null)
    setPreviewFailed(false)
    setContext(null)
    setMenu([])
    init()
  }, [init])

  // the first alcohol dish of a session is asked about; after a yes the next ones are not
  function addToCart(item: MenuItem) {
    if (item.age_check && !ageConfirmed) {
      setAgeQuestion(item)
      return
    }
    setCart((prev) => addToCartLine(prev, item))
  }

  // 「はい」 is recorded on the session at once (a reload before the order is sent does not ask again);
  // 「いいえ」 records nothing and the dish is not put in the cart
  async function answerAge(yes: boolean) {
    const item = ageQuestion
    setAgeQuestion(null)
    if (!yes || !item || !context) return
    try {
      await confirmAge(context.session)
    } catch (err) {
      handleFailure(err)
      return
    }
    setAgeConfirmed(true)
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
      setPreviewFailed(false)
      return
    }
    let current = true
    const timer = window.setTimeout(() => {
      previewCart(session, JSON.parse(cartKey))
        .then((preview) => {
          if (!current) return
          setCartPreview(preview)
          setPreviewFailed(false)
          setError(null) // the total came: an earlier "could not connect" is over
        })
        .catch((err) => {
          if (!current) return
          setCartPreview(null)
          // when the ordering is over a notice takes the place of the page; otherwise the total area says
          // that it has no total
          if (isOrderingOver(classifyFailure(err))) {
            handleFailure(err)
            return
          }
          setPreviewFailed(true)
        })
    }, PREVIEW_DELAY_MS)
    return () => {
      current = false
      window.clearTimeout(timer)
    }
  }, [session, cartKey, order?.grand_total, handleFailure, setError])

  // keep the cart for a reload of the page
  useEffect(() => {
    if (session && cartRestored) saveCart(sessionStorage, session, cart)
  }, [session, cart, cartRestored])
  const cartTotal = cartPreview?.rounded_total ?? null

  async function submitCart() {
    if (!context || cartItems.length === 0) return
    setSubmitting(true)
    setError(null)
    try {
      const payload = toPayload(cart, Boolean(context.capabilities.item_notes_enabled))
      // the answer is sent with an order that has alcohol; the server records it on the session
      const updated = await addItems(context.session, payload, ageConfirmed && hasAgeCheckedDish(cart))
      setOrder(updated)
      setCart({})
    } catch (err) {
      handleFailure(err)
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
      handleFailure(err)
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
      handleFailure(err)
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
    previewFailed,
    closed,
    dismissError,
    ageQuestion,
    answerAge,
  }
}
