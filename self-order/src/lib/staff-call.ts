import type { OrderStatus } from './api'

/**
 * Whether the page says 「スタッフを呼びました」 (and not the button). `status` is the server's last answer (null: not asked
 * yet): when there is one it is the truth, so a call the staff have answered shows the button again. Before the first answer
 * the guest's own press counts.
 */
export function staffCalled(status: OrderStatus | null, pressedHere: boolean): boolean {
  if (!status) return pressedHere
  return (status.open_requests ?? []).some((request) => request.request_type === 'Assistance')
}
