import { useDeviceBootstrap } from './hooks/useDeviceBootstrap'
import DeviceSetup from './layouts/DeviceSetup'
import { NOT_SET_DEVICE_CODE, UNKNOWN_DEVICE_CODE, entryFor } from './lib/device'
import WaitingScreen from './components/WaitingScreen'
import MisconfiguredScreen from './components/MisconfiguredScreen'
import MobileQRLayout from './layouts/MobileQRLayout'
import TabletLayout from './layouts/TabletLayout'
import LandscapeKioskLayout from './layouts/LandscapeKioskLayout'
import PortraitKioskLayout from './layouts/PortraitKioskLayout'
import type { OrderingLayout } from './lib/api'
import { getStoredContext } from './lib/api'
import { t } from './i18n'

const LAYOUTS: Record<OrderingLayout, typeof MobileQRLayout> = {
  Mobile: MobileQRLayout,
  Tablet: TabletLayout,
  'Landscape Kiosk': LandscapeKioskLayout,
  'Portrait Kiosk': PortraitKioskLayout,
}

/**
 * Layout-shell selector. A provisioned device (kiosk/tablet, resolved via
 * useDeviceBootstrap from a stored device credential) picks its layout from
 * the server-returned `deviceContext.layout` — never a client guess — and
 * skips straight to it with an already-resolved context, so it never
 * re-bootstraps via QR token. Anything else (no stored device credential —
 * the QR/mobile case) falls through to MobileQRLayout, which does its own
 * token/session bootstrap via useOrderingSession().
 */
function App() {
  if (window.location.pathname.replace(/\/+$/, '').endsWith('/setup')) return <DeviceSetup />
  return <Shell />
}

function Shell() {
  const { isDevice, screen } = useDeviceBootstrap()

  const entry = entryFor({
    hasDevice: isDevice,
    search: window.location.search,
    hasStoredSession: getStoredContext() !== null,
  })
  if (entry === 'tablet_not_set') return <MisconfiguredScreen code={NOT_SET_DEVICE_CODE} />
  if (!isDevice || entry === 'customer') return <MobileQRLayout />

  if (screen.kind === 'starting') {
    return <div className="flex min-h-screen items-center justify-center text-muted-foreground">{t('app.starting')}</div>
  }
  if (screen.kind === 'rejected') return <MisconfiguredScreen code={UNKNOWN_DEVICE_CODE} />
  if (screen.kind === 'waiting') return <WaitingScreen reason={screen.reason} />
  if (screen.kind === 'misconfigured') return <MisconfiguredScreen code={screen.code} />

  const Layout = LAYOUTS[screen.context.layout] ?? MobileQRLayout
  // a new session is a new page: another key, so nothing of the guests before is left in it
  return <Layout key={screen.generation} initialContext={screen.context} />
}

export default App
