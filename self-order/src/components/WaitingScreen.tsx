import { t } from '../i18n'

interface WaitingScreenProps {
  /** why the guests cannot order yet: the staff have not opened the table, or the shop is closed */
  reason: 'table_closed' | 'store_closed'
}

/** A table tablet while the table is not open for ordering: it asks the server by itself and starts when the staff open the table. */
function WaitingScreen({ reason }: WaitingScreenProps) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background p-8 text-center" role="status">
      <h1 className="text-2xl font-semibold">{t('device.waiting_title')}</h1>
      <p className="max-w-md text-lg text-muted-foreground">
        {reason === 'store_closed' ? t('device.waiting_store') : t('device.waiting_table')}
      </p>
    </div>
  )
}

export default WaitingScreen
