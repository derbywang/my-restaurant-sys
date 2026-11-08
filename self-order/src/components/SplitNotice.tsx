import { t } from '../i18n'

/**
 * The bill of the table was split (会計分割): the order and the amount on this page are this part of it, and what the
 * guests order from here joins this part. A plain note, not an error: the guests can go on ordering.
 */
function SplitNotice({ split, className = '' }: { split?: boolean; className?: string }) {
  if (!split) return null
  return (
    <div className={`rounded-md border bg-muted/50 p-3 text-sm ${className}`} role="note">
      <p className="font-semibold">{t('split.title')}</p>
      <p className="mt-1 text-muted-foreground">{t('split.message')}</p>
    </div>
  )
}

export default SplitNotice
