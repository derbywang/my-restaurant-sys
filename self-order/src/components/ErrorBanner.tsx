import { t } from '../i18n'

interface ErrorBannerProps {
  text: string | null
  onClose: () => void
  className?: string
}

/** The red notice about a problem. It goes away when the next request succeeds; the guest can close it too. */
function ErrorBanner({ text, onClose, className = 'mx-4 mt-3 p-3 text-sm' }: ErrorBannerProps) {
  if (!text) return null
  return (
    <div className={`flex items-start justify-between gap-3 rounded-md bg-destructive/10 text-destructive ${className}`} role="alert">
      <span>{text}</span>
      <button onClick={onClose} aria-label={t('errors.close')} className="shrink-0 px-1 font-semibold leading-none">
        ×
      </button>
    </div>
  )
}

export default ErrorBanner
