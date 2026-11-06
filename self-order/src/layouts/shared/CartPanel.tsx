import { formatCurrency } from '@ury/core'
import type { CartPreview, CustomerOrder, MenuItem, OrderingContext } from '../../lib/api'
import type { CartEntry } from '../../lib/cart'
import CartNote from '../../components/CartNote'
import CartTotals, { cartTotalText } from '../../components/CartTotals'
import { t } from '../../i18n'
import { mergeOrderLines } from '../../lib/order-lines'

interface CartPanelProps {
  context: OrderingContext | null
  order: CustomerOrder | null
  cartItems: CartEntry[]
  cartCount: number
  cartTotal: number | null
  cartPreview: CartPreview | null
  previewFailed: boolean
  submitting: boolean
  billRequested: boolean
  payingOnline: boolean
  onIncrement: (item: MenuItem) => void
  onDecrement: (itemCode: string) => void
  onNoteChange: (itemCode: string, note: string) => void
  onSubmit: () => void
  onRequestBill: () => void
  onPayOnline: () => void
  className?: string
}

/**
 * Persistent order-summary + cart panel shared between TabletLayout and
 * LandscapeKioskLayout. Unlike MobileQRLayout's bottom sheet, this is always
 * visible — no toggle to open/close it.
 */
function CartPanel({
  context,
  order,
  cartItems,
  cartCount,
  cartTotal,
  cartPreview,
  previewFailed,
  submitting,
  billRequested,
  payingOnline,
  onIncrement,
  onDecrement,
  onNoteChange,
  onSubmit,
  onRequestBill,
  onPayOnline,
  className,
}: CartPanelProps) {
  return (
    <aside className={className}>
      <div className="flex-1 overflow-y-auto">
        {order && order.items.length > 0 && (
          <section className="mb-4 rounded-lg border p-3">
            <h2 className="mb-2 text-sm font-medium text-muted-foreground">{t('cart.order_so_far')}</h2>
            <ul className="space-y-1 text-sm">
              {mergeOrderLines(order.items).map((row, idx) => (
                <li key={`${row.item_code}-${idx}`} className="flex justify-between">
                  <span>
                    {row.item_name} × {row.qty}
                    {row.comment && <span className="ml-1 text-xs text-muted-foreground">（{row.comment}）</span>}
                  </span>
                  <span className="tabular-nums">{formatCurrency(row.amount_incl_tax)}</span>
                </li>
              ))}
            </ul>
            <div className="mt-2 flex justify-between border-t pt-2 text-sm font-semibold">
              <span>{t('cart.total_incl_tax')}</span>
              <span className="tabular-nums">{formatCurrency(order.grand_total)}</span>
            </div>
          </section>
        )}

        <section>
          <h2 className="mb-2 text-sm font-medium text-muted-foreground">{t('cart.title')}</h2>
          {cartItems.length === 0 ? (
            <p className="text-sm text-muted-foreground">Tap a menu item to add it to your cart.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {cartItems.map((entry) => (
                <li key={entry.item.item}>
<div className="flex items-center justify-between gap-2">
                  <span className="flex-1">{entry.item.item_name}</span>
                  <span className="flex items-center gap-2">
                    <button
                      onClick={() => onDecrement(entry.item.item)}
                      className="h-7 w-7 rounded-full border text-sm leading-none"
                      aria-label={`Remove one ${entry.item.item_name}`}
                    >
                      −
                    </button>
                    <span className="w-4 text-center">{entry.qty}</span>
                    <button
                      onClick={() => onIncrement(entry.item)}
                      className="h-7 w-7 rounded-full border text-sm leading-none"
                      aria-label={`Add one more ${entry.item.item_name}`}
                    >
                      +
                    </button>
                  </span>
                </div>
{context?.capabilities.item_notes_enabled && (
<CartNote itemName={entry.item.item_name} value={entry.note} onChange={(value) => onNoteChange(entry.item.item, value)} />
)}
</li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <div className="border-t pt-3">
        <div className="mb-3 flex items-center justify-between text-sm font-semibold">
          <span>
            {t('cart.items', { count: cartCount })}
          </span>
          <span className="tabular-nums">{cartTotalText(cartTotal, previewFailed)}</span>
        </div>
        <CartTotals preview={cartPreview} failed={previewFailed} />
        <button
          onClick={onSubmit}
          disabled={submitting || cartCount === 0}
          className="w-full rounded-md bg-primary py-3 font-medium text-primary-foreground disabled:opacity-50"
        >
          {submitting ? t('cart.placing') : t('cart.place')}
        </button>
        {context?.capabilities.customer_payment_enabled && order && !order.billed && (
          <button
            className="mt-2 w-full rounded-md bg-primary py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
            disabled={payingOnline}
            onClick={onPayOnline}
          >
            {payingOnline ? t('pay.starting') : t('pay.online')}
          </button>
        )}
        {context?.capabilities.request_bill_enabled && order && !order.billed && (
          <button
            className="mt-2 w-full rounded-md border py-2 text-sm font-medium disabled:opacity-50"
            disabled={billRequested}
            onClick={onRequestBill}
          >
            {billRequested ? t('pay.bill_requested') : t('pay.request_bill')}
          </button>
        )}
      </div>
    </aside>
  )
}

export default CartPanel
