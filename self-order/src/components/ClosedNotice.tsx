import { t } from '../i18n'
import type { FailureKind } from '../lib/failure'

interface ClosedNoticeProps {
  kind: FailureKind
}

/**
 * Shown over the page when the ordering is over (the table was closed or opened again for the next guests, the
 * shop is closed, the order is finished, the session ran out). The cart is gone and nothing can be ordered from
 * this page, so nothing of the menu is left to press.
 */
function ClosedNotice({ kind }: ClosedNoticeProps) {
  return (
    <div
      className="fixed inset-0 z-[60] flex flex-col items-center justify-center gap-6 bg-background p-8 text-center"
      role="alert"
    >
      <h1 className="text-xl font-semibold">{t(`closed.${kind}.title`)}</h1>
      <p className="max-w-sm text-base text-muted-foreground">{t(`closed.${kind}.message`)}</p>
      <button
        onClick={() => window.location.reload()}
        className="rounded-md border px-6 py-3 text-base font-medium"
      >
        {t('closed.reload')}
      </button>
    </div>
  )
}

export default ClosedNotice
