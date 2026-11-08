import type { DeviceStatus } from './device'
import { call } from '@ury/core'

const M = 'ury.ury.api.self_ordering'

export interface OrderingCapabilities {
  product_detail_enabled: boolean
  show_item_images: boolean
  show_item_descriptions: boolean
  item_notes_enabled: boolean
  request_bill_enabled: boolean
  customer_payment_enabled: boolean
  payment_link_enabled: boolean
  pay_at_counter_enabled: boolean
  add_to_running_table_enabled: boolean
}

export type OrderingLayout = 'Mobile' | 'Tablet' | 'Landscape Kiosk' | 'Portrait Kiosk'

export interface OrderingContext {
  session: string
  source: string
  restaurant: string
  table: string | null
  layout: OrderingLayout
  capabilities: OrderingCapabilities
}

export interface MenuItem {
  item: string
  item_name: string
  /** The price of one with the tax, worked out by the server; the price without tax is never sent. */
  price_incl_tax: number
  /** The guest is asked "20歳以上ですか？" before this dish goes in the cart (alcohol). */
  age_check: boolean
  special_dish: number
  disabled: number
  item_image: string | null
  course: string | null
  course_label: string | null
}

export interface MenuResponse {
  /** The guest already answered "20歳以上ですか？" with yes in this session. */
  age_confirmed?: boolean
  items: MenuItem[]
  modified_time: string | null
  name: string | null
}

export interface OrderItem {
  item_code: string
  item_name: string
  qty: number
  comment: string | null
  price_incl_tax: number
  amount_incl_tax: number
}

export interface CustomerOrder {
  invoice: string | null
  table?: string | null
  order_type?: string
  // Pickup reference code (derived from the invoice name) — the only
  // identifier a QR Pickup customer has, since there's no table to point
  // to. Present (possibly null before an order exists) on every response.
  pickup_code?: string | null
  items: OrderItem[]
  /** What the bill will be for all of the order, with the tax. */
  grand_total: number
  billed: boolean
  /** the bill of the table was split and another part of it is still there */
  split?: boolean
}

/** What the cart comes to with the tax, from the server (`preview_customer_cart`). */
export interface CartPreview {
  rounded_total: number
  /** The dishes already ordered, which are part of `rounded_total`. */
  ordered_total: number
  taxes: { rate: number; taxable_amount: number; tax_amount: number }[]
}

export interface OrderStatus {
  session_status: string
  invoice: string | null
  billed?: boolean
  submitted?: boolean
  open_requests?: { name: string; request_type: string; status: string }[]
}

// Persist the full ordering context (not just the opaque session token)
// across the browser session — a page refresh/resume must not force a
// customer to rescan, and must not lose capabilities/table/layout either
// (a session-token-only resume can't reconstruct those without another
// round trip the backend doesn't offer for an already-open session).
const SESSION_KEY = 'ury_order_session'
const CONTEXT_KEY = 'ury_order_context'
// the ordering code (from the QR link) the stored session was made from; see lib/resume.ts
const TOKEN_KEY = 'ury_order_token'

export function getStoredToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY)
}

export function getStoredSession(): string | null {
  return sessionStorage.getItem(SESSION_KEY)
}

export function getStoredContext(): OrderingContext | null {
  const raw = sessionStorage.getItem(CONTEXT_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as OrderingContext
  } catch {
    return null
  }
}

function storeContext(context: OrderingContext) {
  sessionStorage.setItem(SESSION_KEY, context.session)
  sessionStorage.setItem(CONTEXT_KEY, JSON.stringify(context))
}

// Every whitelisted Frappe method response is wrapped as {"message": <actual
// return value>} — call.get/call.post return that whole envelope as-is
// (frappe-js-sdk does not unwrap it; see pos/src/lib/menu-api.ts's
// GetMenuResponse for the same established pattern in this codebase). Every
// function below must unwrap `.message` itself. Missing this doesn't throw —
// it silently produces `undefined` fields (e.g. `context.session` would be
// undefined instead of a string), which cascades into every subsequent call
// silently sending no value for that parameter at all. Confirmed live via
// browser network capture: get_customer_menu was called with an entirely
// empty query string because the "session" it was given was undefined.
interface FrappeResponse<T> {
  message: T
}

export async function bootstrap(token: string): Promise<OrderingContext> {
  const response = await call.get<FrappeResponse<OrderingContext>>(`${M}.get_ordering_context`, { token })
  storeContext(response.message)
  sessionStorage.setItem(TOKEN_KEY, token)
  return response.message
}

export async function bootstrapDevice(deviceId: string, deviceCredential: string): Promise<OrderingContext> {
  const response = await call.get<FrappeResponse<OrderingContext>>(`${M}.get_ordering_context`, {
    device_id: deviceId,
    device_credential: deviceCredential,
  })
  storeContext(response.message)
  return response.message
}

export async function getDeviceStatus(deviceId: string, deviceCredential: string): Promise<DeviceStatus> {
  const response = await call.get<FrappeResponse<DeviceStatus>>(`${M}.device_status`, {
    device_id: deviceId,
    device_credential: deviceCredential,
  })
  return response.message
}

export async function getMenu(session: string): Promise<MenuResponse> {
  const response = await call.get<FrappeResponse<MenuResponse>>(`${M}.get_customer_menu`, { session })
  return response.message
}

export async function getCurrentOrder(session: string): Promise<CustomerOrder> {
  const response = await call.get<FrappeResponse<CustomerOrder>>(`${M}.get_customer_order`, { session })
  return response.message
}

export async function previewCart(
  session: string,
  items: { item: string; qty: number }[],
): Promise<CartPreview> {
  const response = await call.post<FrappeResponse<CartPreview>>(`${M}.preview_customer_cart`, {
    session,
    items: JSON.stringify(items),
  })
  return response.message
}

/** The guest answered 「はい」 to 「20歳以上ですか？」: the server keeps it on the session, so a reload does not ask again. */
export async function confirmAge(session: string): Promise<void> {
  await call.post<FrappeResponse<{ age_confirmed: boolean }>>(`${M}.confirm_age`, { session })
}

export async function addItems(
  session: string,
  items: { item: string; qty: number; comment?: string }[],
  ageConfirmed = false,
): Promise<CustomerOrder> {
  const response = await call.post<FrappeResponse<CustomerOrder>>(`${M}.add_customer_items`, {
    session,
    items: JSON.stringify(items),
    age_confirmed: ageConfirmed ? 1 : 0,
  })
  return response.message
}

export async function requestBill(session: string): Promise<{ status: string; request: string }> {
  const response = await call.post<FrappeResponse<{ status: string; request: string }>>(`${M}.request_bill`, { session })
  return response.message
}

export async function getStatus(session: string): Promise<OrderStatus> {
  const response = await call.get<FrappeResponse<OrderStatus>>(`${M}.get_order_status`, { session })
  return response.message
}

export interface PaymentRequestResult {
  payment_request: string
  amount: number
  currency: string
  payment_url: string | null
  status: string
}

export interface PaymentStatusResult {
  status: string | null
  payment_request?: string
  amount?: number
}

export async function createPaymentRequest(session: string): Promise<PaymentRequestResult> {
  const response = await call.post<FrappeResponse<PaymentRequestResult>>(`${M}.create_payment_request`, { session })
  return response.message
}

export async function getPaymentStatus(session: string): Promise<PaymentStatusResult> {
  const response = await call.get<FrappeResponse<PaymentStatusResult>>(`${M}.get_payment_status`, { session })
  return response.message
}

export async function sharePaymentLink(
  session: string,
  recipient: string,
): Promise<{ status: string; payment_request: string }> {
  const response = await call.post<FrappeResponse<{ status: string; payment_request: string }>>(
    `${M}.share_payment_link`,
    { session, recipient },
  )
  return response.message
}
