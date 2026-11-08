import { useEffect, useState } from 'react'
import { parseSetupFragment, saveDevice, setupDoneUrl } from '../lib/device'
import { t } from '../i18n'

/**
 * `/order/setup#device=...&credential=...`: the link the staff issue in the Desk. Keeps the device and the
 * credential on this tablet, takes them off the address bar and starts. The fragment is never sent to the server.
 */
function DeviceSetup() {
  const [done, setDone] = useState<boolean | null>(null)

  useEffect(() => {
    const device = parseSetupFragment(window.location.hash)
    if (!device) {
      setDone(false)
      return
    }
    saveDevice(device)
    window.history.replaceState(null, '', window.location.pathname)
    setDone(true)
    const timer = window.setTimeout(() => window.location.replace(setupDoneUrl()), 1500)
    return () => window.clearTimeout(timer)
  }, [])

  return (
    <div className="flex min-h-screen items-center justify-center p-8 text-center text-lg" role="status">
      {done === null ? t('device.setup_working') : done ? t('device.setup_done') : t('device.setup_failed')}
    </div>
  )
}

export default DeviceSetup
