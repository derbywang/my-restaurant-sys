import { t } from '../i18n'
import { UNKNOWN_DEVICE_CODE } from '../lib/device'

interface MisconfiguredScreenProps {
  /** for the staff: what is wrong (E-DEVICE-ORDERING-OFF, E-PROFILE-OFF, E-NO-TABLE, E-TABLE-BRANCH, E-DEVICE-UNKNOWN) */
  code: string
}

/** The set-up of this tablet (or of the shop's ordering) is not right: never shown as "waiting", so that it is seen at once. */
function MisconfiguredScreen({ code }: MisconfiguredScreenProps) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background p-8 text-center" role="alert">
      <h1 className="text-2xl font-semibold text-destructive">
        {code === UNKNOWN_DEVICE_CODE ? t('device.not_recognized_title') : t('device.misconfigured_title')}
      </h1>
      <p className="max-w-md text-lg text-muted-foreground">{t('device.misconfigured_message')}</p>
      <p className="rounded-md border px-4 py-2 font-mono text-base">{code}</p>
    </div>
  )
}

export default MisconfiguredScreen
