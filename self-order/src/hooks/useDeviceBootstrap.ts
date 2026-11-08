import { useEffect, useRef, useState } from 'react'
import { bootstrapDevice, getDeviceStatus, type OrderingContext } from '../lib/api'
import { decide, pollDelay, readDevice, screenFor, type DevicePhase, type DeviceStatus } from '../lib/device'

export type DeviceScreen =
  | { kind: 'starting' }
  | { kind: 'waiting'; reason: 'table_closed' | 'store_closed' }
  | { kind: 'misconfigured'; code: string }
  | { kind: 'ordering'; context: OrderingContext; generation: number }
  | { kind: 'rejected' }

function isRefused(error: unknown): boolean {
  const status = (error as { httpStatus?: number; status?: number })?.httpStatus ?? (error as { status?: number })?.status
  return status === 401 || status === 403
}

/**
 * A provisioned table tablet (its device and credential are kept by `DeviceSetup`): asks the server whether the table
 * is open, and by itself starts a session when the staff open it, drops it when the table closes, and starts a new
 * one when the table is opened again for the next guests. While the guests order it asks every little while too, which
 * is also how the server knows the tablet is alive.
 */
export function useDeviceBootstrap() {
  const [device] = useState(() => readDevice())
  const [screen, setScreen] = useState<DeviceScreen>({ kind: 'starting' })
  const phase = useRef<DevicePhase>({ kind: 'waiting' })
  const generation = useRef(0)

  useEffect(() => {
    if (!device) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined

    async function ask() {
      let delay = pollDelay(phase.current.kind)
      try {
        const status: DeviceStatus = await getDeviceStatus(device!.deviceId, device!.credential)
        if (cancelled) return
        const action = decide(phase.current, status)
        if (action === 'start' || action === 'restart') {
          const context = await bootstrapDevice(device!.deviceId, device!.credential)
          if (cancelled) return
          phase.current = { kind: 'ordering', opening: status.opening }
          generation.current += 1
          setScreen({ kind: 'ordering', context, generation: generation.current })
        } else if (action === 'wait') {
          phase.current = { kind: 'waiting' }
          setScreen(screenFor(status))
        }
      } catch (error) {
        if (cancelled) return
        if (isRefused(error)) {
          setScreen({ kind: 'rejected' })
          return
        }
        // the network or the server is away for a moment: a tablet that is ordering goes on, one that waits waits
        if (phase.current.kind === 'waiting') setScreen((now) => (now.kind === 'starting' ? { kind: 'waiting', reason: 'table_closed' } : now))
        delay = pollDelay('waiting')
      }
      if (!cancelled) timer = setTimeout(ask, delay)
    }

    ask()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [device])

  return { isDevice: device !== null, screen }
}
