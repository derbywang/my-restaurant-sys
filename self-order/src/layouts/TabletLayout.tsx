import AgeConfirmDialog from '../components/AgeConfirmDialog'
import ClosedNotice from '../components/ClosedNotice'
import BillSwitchNotice from '../components/BillSwitchNotice'
import ErrorBanner from '../components/ErrorBanner'
import { useRef, useState } from 'react'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@ury/ui'
import { useIdleReset } from '../hooks/useIdleReset'
import { useOrderingSession } from '../hooks/useOrderingSession'
import type { OrderingContext } from '../lib/api'
import { isTableTablet } from '../lib/device'
import CartPanel from './shared/CartPanel'
import MenuGrid from './shared/MenuGrid'
import { t } from '../i18n'
import LanguageSwitcher from '../components/LanguageSwitcher'

const IDLE_WARN_MS = 60000
const IDLE_RESET_GRACE_MS = 15000

interface LayoutProps {
  initialContext?: OrderingContext
}

/**
 * Two-pane layout for a tablet, portrait or landscape, handed to a customer
 * or fixed at a table. Left/main pane is a scrollable menu grid; right pane
 * is a persistent order summary + cart (not a bottom sheet like
 * MobileQRLayout — always visible, no toggle).
 */
function TabletLayout({ initialContext }: LayoutProps) {
  const {
    context,
    menu,
    order,
    cart,
    loading,
    submitting,
    error,
    billRequested,
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
    billSwitch,
    dismissBillSwitch,
    language,
    changeLanguage,
  } = useOrderingSession(initialContext)

  const [showIdleWarning, setShowIdleWarning] = useState(false)
  const idleResetTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  // a tablet at a table: the guests talk it over, nothing is cleared by itself and the button only empties the cart
  const atTable = isTableTablet(context)

  function handleReset() {
    if (window.confirm(atTable ? t('confirm.clear_cart') : t('confirm.new_order'))) {
      resetSession()
    }
  }

  // Unattended-kiosk protection: warn after IDLE_WARN_MS of no interaction,
  // then reset after an additional IDLE_RESET_GRACE_MS if the guest doesn't
  // respond. Never fires mid-checkout — submitting/payingOnline gate both
  // the warning and the reset itself.
  useIdleReset(() => {
    if (atTable || submitting || payingOnline) return
    setShowIdleWarning(true)
    idleResetTimerRef.current = setTimeout(() => {
      setShowIdleWarning(false)
      if (!submitting && !payingOnline) {
        resetSession()
      }
    }, IDLE_RESET_GRACE_MS)
  }, IDLE_WARN_MS)

  function handleStillHere() {
    clearTimeout(idleResetTimerRef.current)
    setShowIdleWarning(false)
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

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      {closed && <ClosedNotice kind={closed} />}
      <AgeConfirmDialog item={ageQuestion} onAnswer={answerAge} />
      <header className="flex items-center justify-between border-b bg-background/95 px-6 py-4">
        <h1 className="text-xl font-semibold">
          {context?.table ? t('header.table', { table: context.table }) : t('header.pickup')}
        </h1>
        <div className="flex items-center gap-3">
          <LanguageSwitcher languages={context?.languages} current={language} onChange={changeLanguage} size="md" />
          <button
            onClick={handleReset}
            className="rounded-md border px-3 py-2 text-sm font-medium text-muted-foreground"
          >
            {atTable ? t('header.clear_cart') : t('header.new_order')}
          </button>
        </div>
      </header>

      <BillSwitchNotice open={billSwitch} onClose={dismissBillSwitch} className="mx-6 mt-3" />

      <ErrorBanner text={error} onClose={dismissError} className="mx-6 mt-3 p-3 text-sm" />

      <div className="flex flex-1 overflow-hidden">
        <main className="w-[68%] overflow-y-auto p-6">
          <MenuGrid
            menu={menu}
            cart={cart}
            capabilities={context?.capabilities}
            onAdd={addToCart}
            gridClassName="grid grid-cols-3 gap-4 lg:grid-cols-4"
            cardClassName="flex min-w-[150px] flex-col overflow-hidden rounded-xl border text-left transition active:scale-[0.98]"
            imageClassName="h-32 w-full object-cover"
          />
        </main>

        <CartPanel
          context={context}
          order={order}
          cartItems={cartItems}
          cartCount={cartCount}
          cartTotal={cartTotal}
          cartPreview={cartPreview}
          previewFailed={previewFailed}
          submitting={submitting}
          billRequested={billRequested}
          payingOnline={payingOnline}
          onIncrement={addToCart}
          onDecrement={decrementCart}
          onNoteChange={setCartNote}
          onSubmit={submitCart}
          onRequestBill={handleRequestBill}
          onPayOnline={payOnline}
          className="flex w-[32%] flex-col overflow-hidden border-l bg-background p-4"
        />
      </div>

      <Dialog open={showIdleWarning} onOpenChange={(open) => !open && handleStillHere()}>
        <DialogContent onClose={handleStillHere}>
          <DialogHeader>
            <DialogTitle>{t('idle.title')}</DialogTitle>
          </DialogHeader>
          <DialogFooter>
            <button
              onClick={handleStillHere}
              className="w-full rounded-md bg-primary py-3 text-base font-medium text-primary-foreground"
            >
              {t('idle.still_here')}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export default TabletLayout
