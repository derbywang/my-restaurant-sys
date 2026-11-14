// A waiter works on the shift the cashier opened: she has none of her own and may not open one. Before the waiter screens
// the POS asks whether the shop's register is open (`get_shift_state`); the cashier's own opening screen stays as it was.
import { call } from '@ury/core';
import { isWaiterOnly, type PosPermissions } from './pos-permissions';

/** How often the waiting page asks again. */
export const RECHECK_MS = 30_000;

export interface ShiftState {
  open: boolean;
  opened_by: string | null;
}

export type OpeningRoute = 'loading' | 'own_shift' | 'open' | 'closed';

/**
 * Which way the POS opens. Not knowing the permissions (or, for a waiter, the answer) is `loading`: the user is neither
 * let in nor shown the opening screen on a guess.
 */
export function routeForOpening(permissions: PosPermissions | null, shift: ShiftState | null): OpeningRoute {
  if (!permissions) return 'loading';
  if (!isWaiterOnly(permissions)) return 'own_shift';
  if (!shift) return 'loading';
  return shift.open ? 'open' : 'closed';
}

export async function getShiftState(): Promise<ShiftState> {
  const response = await call.get<{ message: ShiftState }>('ury.ury.api.pos_permissions.get_shift_state');
  return response.message;
}

/** The type of each payment mode of the opening screen, by name (the cash mode is shown as 「現金」). */
export function modeTypesOf(modes: { mode_of_payment: string; type?: string | null }[]): Record<string, string> {
  const types: Record<string, string> = {};
  for (const mode of modes) {
    if (mode.type) types[mode.mode_of_payment] = mode.type;
  }
  return types;
}
