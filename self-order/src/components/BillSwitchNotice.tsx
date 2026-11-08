import { t } from '../i18n'

interface BillSwitchNoticeProps {
  open: boolean
  onClose: () => void
  className?: string
}

/**
 * The bill of the guests was printed (a split bill) and this page now follows the part that is still open: they are
 * told where the next dishes go, and that a guest who was given a bill asks the staff to add more. Stays until
 * the guests close it; a notice, not an error.
 */
function BillSwitchNotice({ open, onClose, className = '' }: BillSwitchNoticeProps) {
  if (!open) return null
  return (
    <div className={`rounded-md border-2 border-amber-400 bg-amber-50 p-3 text-sm text-amber-950 ${className}`} role="status">
      <div className="flex items-start justify-between gap-3">
        <p className="font-semibold">{t('bill_switch.title')}</p>
        <button onClick={onClose} className="shrink-0 rounded-md border border-amber-400 px-2 py-0.5 text-xs font-medium">
          {t('errors.close')}
        </button>
      </div>
      <p className="mt-1">{t('bill_switch.message')}</p>
      <p className="mt-1 font-medium">{t('bill_switch.staff')}</p>
    </div>
  )
}

export default BillSwitchNotice
