import CallStaffButton from '../components/CallStaffButton'
import { useState } from 'react'
import AgeConfirmDialog from '../components/AgeConfirmDialog'
import ItemOptionsDialog from '../components/ItemOptionsDialog'
import ClosedNotice from '../components/ClosedNotice'
import BillSwitchNotice from '../components/BillSwitchNotice'
import ErrorBanner from '../components/ErrorBanner'
import SplitNotice from '../components/SplitNotice'
import { formatCurrency } from '@ury/core'
import { useOrderingSession } from '../hooks/useOrderingSession'
import CartLineRow from '../components/CartLineRow'
import { priceText } from './shared/MenuGrid'
import { cartCountFor } from '../lib/cart'
import CartTotals, { cartTotalText } from '../components/CartTotals'
import { t } from '../i18n'
import { cartCountText } from '../lib/cart-text'
import LanguageSwitcher from '../components/LanguageSwitcher'
import { mergeOrderLines } from '../lib/order-lines'
import type { OrderingContext } from '../lib/api'

interface LayoutProps {
  initialContext?: OrderingContext
}

function MobileQRLayout({ initialContext }: LayoutProps) {
  const {
    context,
    menu,
    order,
    cart,
    loading,
    submitting,
    error,
    billRequested,
    staffCalled,
    handleCallStaff,
    paymentRequest,
    payingOnline,
    selectItem,
    addLine,
    optionsItem,
    closeOptions,
    incrementCart,
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
    billSwitch,
    dismissBillSwitch,
    language,
    changeLanguage,
  } = useOrderingSession(initialContext)

  // the cart is one bar at the bottom (the count, the total, the order button); the lines open on a tap and scroll inside
  const [cartOpen, setCartOpen] = useState(false)

  function handleStartOver() {
    if (window.confirm(t('confirm.start_over'))) {
      resetSession()
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-muted-foreground">
        {t('menu.loading')}
      </div>
    )
  }

  if (error && !context) {
    return (
      <div className="flex min-h-screen items-center justify-center p-6 text-center text-destructive">
        {error}
      </div>
    )
  }

  // `source` (not the absence of a table) is the authoritative signal for
  // pickup mode — set server-side by _verify_qr_token/_resolve_device, never
  // guessed from context.table being falsy.
  const isPickup = context?.source === 'QR Pickup'

  return (
    <div className="min-h-screen pb-36">
      {closed && <ClosedNotice kind={closed} />}
      <AgeConfirmDialog item={ageQuestion} onAnswer={answerAge} />
      <ItemOptionsDialog item={optionsItem} session={context?.session} language={language} capabilities={context?.capabilities} onAdd={addLine} onClose={closeOptions} />
      <header className="sticky top-0 z-10 flex items-center justify-between gap-2 border-b bg-background/95 px-3 py-3 backdrop-blur">
        <h1 className="min-w-0 truncate whitespace-nowrap text-base font-semibold">
          {isPickup ? t('header.pickup') : context?.table ? t('header.table', { table: context.table }) : t('header.order')}
        </h1>
        <div className="flex shrink-0 items-center gap-2">
          <CallStaffButton enabled={Boolean(context?.capabilities.call_staff_enabled)} called={staffCalled} onCall={handleCallStaff} />
          <LanguageSwitcher languages={context?.languages} current={language} onChange={changeLanguage} variant="menu" />
          <button
            onClick={handleStartOver}
            className="whitespace-nowrap rounded-md border px-2 py-1.5 text-xs font-medium text-muted-foreground"
          >
            {t('header.start_over')}
          </button>
        </div>
      </header>

      <BillSwitchNotice open={billSwitch} onClose={dismissBillSwitch} className="mx-4 mt-3" />

      <ErrorBanner text={error} onClose={dismissError} className="mx-4 mt-3 p-3 text-sm" />

      <SplitNotice split={order?.split} className="mx-4 mt-4" />

      {order && order.items.length > 0 && (
        <section className="mx-4 mt-4 rounded-lg border p-3">
          <h2 className="mb-2 text-sm font-medium text-muted-foreground">{t('cart.order_so_far')}</h2>
          {isPickup && order.pickup_code && (
            <p className="mb-2 rounded-md bg-muted p-2 text-center text-sm font-semibold">
              Pickup code: {order.pickup_code}
            </p>
          )}
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
          {context?.capabilities.customer_payment_enabled && !order.billed && (
            <button
              className="mt-3 w-full rounded-md bg-primary py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
              disabled={payingOnline}
              onClick={payOnline}
            >
              {payingOnline ? t('pay.starting') : t('pay.online')}
            </button>
          )}
          {paymentRequest && !paymentRequest.payment_url && (
            <p className="mt-2 text-xs text-muted-foreground">
              {t('pay.request_created', { amount: paymentRequest.amount, currency: paymentRequest.currency })}
            </p>
          )}
          {!isPickup && context?.capabilities.request_bill_enabled && !order.billed && (
            billRequested ? (
              <p className="mt-3 w-full rounded-md bg-amber-50 py-2 text-center text-sm font-medium text-amber-900">
                {t('pay.bill_requested')}
              </p>
            ) : (
              <button className="mt-3 w-full rounded-md border py-2 text-sm font-medium" onClick={handleRequestBill}>
                {t('pay.request_bill')}
              </button>
            )
          )}
        </section>
      )}

      <section className="mx-4 mt-4 grid grid-cols-2 gap-3">
        {menu.map((item) => (
          <button
            key={item.item}
            onClick={() => selectItem(item)}
            className="flex flex-col overflow-hidden rounded-lg border text-left transition active:scale-[0.98]"
          >
            {context?.capabilities.show_item_images && item.item_image && (
              <img src={item.item_image} alt={item.item_name} className="h-24 w-full object-cover" />
            )}
            <div className="p-2">
              <div className="text-sm font-medium">{item.item_name}</div>
              <div className="text-sm text-muted-foreground tabular-nums">{priceText(item)}{t('price.incl_tax')}</div>
              {cartCountFor(cart, item.item) > 0 && (
                <div className="mt-1 text-xs font-semibold text-primary">{t('cart.in_cart', { count: cartCountFor(cart, item.item) })}</div>
              )}
            </div>
          </button>
        ))}
      </section>

      {cartCount > 0 && (
        <div className="fixed inset-x-0 bottom-0 border-t bg-background px-4 pb-3 pt-2">
          {cartOpen && (
            <div className="mb-2 max-h-[45vh] overflow-y-auto border-b pb-2">
              <ul className="space-y-2 text-sm">
                {cartItems.map((entry) => (
                  <CartLineRow
                    key={entry.key}
                    entry={entry}
                    notesEnabled={Boolean(context?.capabilities.item_notes_enabled)}
                    onIncrement={incrementCart}
                    onDecrement={decrementCart}
                    onNote={setCartNote}
                    buttonClassName="h-7 w-7 rounded-full border text-sm leading-none"
                  />
                ))}
              </ul>
              <div className="mt-2">
                <CartTotals preview={cartPreview} failed={previewFailed} />
              </div>
            </div>
          )}
          <button
            type="button"
            onClick={() => setCartOpen((open) => !open)}
            aria-expanded={cartOpen}
            className="mb-2 flex w-full items-center justify-between gap-2 text-sm font-semibold"
          >
            <span className="whitespace-nowrap">{cartCountText(cartCount)}</span>
            <span className="tabular-nums">{cartTotalText(cartTotal, previewFailed)}</span>
            <span className="whitespace-nowrap rounded-md border px-2 py-1 text-xs font-medium text-primary">
              {cartOpen ? t('cart.hide') : t('cart.view')}
            </span>
          </button>
          <button
            onClick={submitCart}
            disabled={submitting}
            className="w-full rounded-md bg-primary py-3 font-medium text-primary-foreground disabled:opacity-50"
          >
            {submitting ? t('cart.placing') : t('cart.place')}
          </button>
        </div>
      )}
    </div>
  )
}

export default MobileQRLayout
