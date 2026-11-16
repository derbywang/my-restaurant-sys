import { t } from '../i18n'

interface CallStaffButtonProps {
  /** the shop has the call switched on and the guest is at a table */
  enabled: boolean
  called: boolean
  onCall: () => void
  className?: string
}

/** 「スタッフを呼ぶ」: always in sight in the header of the page; after the press it says the staff were called. */
export default function CallStaffButton({ enabled, called, onCall, className = '' }: CallStaffButtonProps) {
  if (!enabled) return null
  if (called) {
    return (
      <p role="status" className={`rounded-md bg-amber-50 px-2 py-1.5 text-xs font-medium text-amber-900 ${className}`}>
        {t('staff.called')}
      </p>
    )
  }
  return (
    <button
      type="button"
      data-testid="call-staff"
      onClick={onCall}
      className={`whitespace-nowrap rounded-md border px-2 py-1.5 text-xs font-medium ${className}`}
    >
      {t('staff.call')}
    </button>
  )
}
