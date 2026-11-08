import { tokenFromSearch } from './qr-link'

// A table tablet: the credentials it keeps, the link that sets it up, and what it does while the table is closed.

export const DEVICE_ID_KEY = 'ury_device_id'
export const DEVICE_CREDENTIAL_KEY = 'ury_device_credential'

export interface DeviceCredentials {
  deviceId: string
  credential: string
}

/** What `device_status` answers. `opening` is another value each time the staff open the table. */
export interface DeviceStatus {
  state: 'open' | 'table_closed' | 'store_closed' | 'not_configured'
  opening: string | null
  /** with `not_configured`: what is wrong, for the staff (E-DEVICE-ORDERING-OFF, E-PROFILE-OFF, E-NO-TABLE, E-TABLE-BRANCH) */
  code?: string
}

/** The tablet is not known to the server: its credential is wrong, it was issued again, or the device was stopped or deleted. */
export const UNKNOWN_DEVICE_CODE = 'E-DEVICE-UNKNOWN'

/** The tablet has no credential (the data of the site was cleared): it must be set up again with the link of the staff. */
export const NOT_SET_DEVICE_CODE = 'E-DEVICE-NOT-SET'

/**
 * The mark of a tablet in its address (`/order/?tablet=1`, the page after the set-up, which the staff put on the home
 * screen). Safari clears the storage but not the address. A phone never has it: the link of the QR code is made by the
 * server with the code of the table only.
 */
export const TABLET_MARK_PARAM = 'tablet'

export function setupDoneUrl(): string {
  return `/order/?${TABLET_MARK_PARAM}=1`
}

/**
 * Who opened the page: a tablet with its credential (`device`), a tablet whose credential is gone (`tablet_not_set`:
 * only with the mark, no code and no session) or a phone (`customer`, also when it lost its code: it gets the message
 * to scan the QR code again). The code of a table always wins: a guest is never shown the screen for the staff.
 */
export function entryFor(page: {
  hasDevice: boolean
  search: string
  hasStoredSession: boolean
}): 'device' | 'tablet_not_set' | 'customer' {
  const params = new URLSearchParams(page.search)
  if (tokenFromSearch(page.search)) return 'customer'
  if (page.hasDevice) return 'device'
  if (page.hasStoredSession) return 'customer'
  return params.get(TABLET_MARK_PARAM) === '1' ? 'tablet_not_set' : 'customer'
}

/** The codes of `device_status` (set-up mistakes) and the one above: what the staff read out to the administrator. */
export const DEVICE_ERROR_CODES = ['E-PROFILE-OFF', 'E-DEVICE-ORDERING-OFF', 'E-NO-TABLE', 'E-TABLE-BRANCH', UNKNOWN_DEVICE_CODE, NOT_SET_DEVICE_CODE]

/** What a tablet shows when it cannot be ordered at: waiting (nobody has done anything wrong) or a mistake in the set-up. */
export type DeviceWait =
  | { kind: 'waiting'; reason: 'table_closed' | 'store_closed' }
  | { kind: 'misconfigured'; code: string }

/** A mistake in the set-up must never look like "the table is not open yet". */
export function screenFor(status: DeviceStatus): DeviceWait {
  if (status.state === 'not_configured') return { kind: 'misconfigured', code: status.code || 'E-UNKNOWN' }
  return { kind: 'waiting', reason: status.state === 'store_closed' ? 'store_closed' : 'table_closed' }
}

export type DevicePhase = { kind: 'waiting' } | { kind: 'ordering'; opening: string | null }

/** The device and the credential in the fragment of the set-up link (`#device=...&credential=...`). */
export function parseSetupFragment(fragment: string): DeviceCredentials | null {
  const params = new URLSearchParams(fragment.replace(/^#/, ''))
  const deviceId = (params.get('device') ?? '').trim()
  const credential = (params.get('credential') ?? '').trim()
  return deviceId && credential ? { deviceId, credential } : null
}

export function readDevice(storage: Pick<Storage, 'getItem'> = localStorage): DeviceCredentials | null {
  const deviceId = storage.getItem(DEVICE_ID_KEY)
  const credential = storage.getItem(DEVICE_CREDENTIAL_KEY)
  return deviceId && credential ? { deviceId, credential } : null
}

export function saveDevice(device: DeviceCredentials, storage: Pick<Storage, 'setItem'> = localStorage) {
  storage.setItem(DEVICE_ID_KEY, device.deviceId)
  storage.setItem(DEVICE_CREDENTIAL_KEY, device.credential)
}

/**
 * What to do with the answer of the server:
 * start (the table just opened), keep (the same opening goes on), restart (opened again for the next guests: the
 * old session is no good), wait (closed: the cart and the order of the guests before are dropped).
 */
export function decide(current: DevicePhase, status: DeviceStatus): 'start' | 'keep' | 'restart' | 'wait' {
  if (status.state !== 'open') return 'wait'
  if (current.kind === 'waiting') return 'start'
  return current.opening === status.opening ? 'keep' : 'restart'
}

/** Milliseconds until the next question: often while it waits (the staff opened the table, the guests sit down). */
export function pollDelay(kind: DevicePhase['kind']): number {
  return kind === 'waiting' ? 5000 : 20000
}

/**
 * A tablet that stays at its table (the session comes from its device, `Table Tablet`): the guests talk it over, and
 * the session ends when the staff close the table. It does not clear the cart of the guests after a while of no
 * touch (a kiosk does), and its button only empties the cart, it does not begin "a new order".
 */
export function isTableTablet(context: { source?: string } | null | undefined): boolean {
  return context?.source === 'Table Tablet'
}
