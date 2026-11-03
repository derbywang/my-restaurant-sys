// What the current user may do in the POS. The server answers (`get_pos_permissions`, from the
// DocType permissions); the screens only show what is allowed. Nothing here knows a role name.
import { call, isPermissionError, parseFrappeError } from '@ury/core';

export interface PosPermissions {
  take_orders: boolean;
  print_bill: boolean;
  settle_payment: boolean;
  cancel_order: boolean;
  apply_discount: boolean;
  merge_bills: boolean;
  unmerge_bills: boolean;
  split_bill: boolean;
  open_shift: boolean;
  close_shift: boolean;
}

export const NO_PERMISSIONS: PosPermissions = {
  take_orders: false,
  print_bill: false,
  settle_payment: false,
  cancel_order: false,
  apply_discount: false,
  merge_bills: false,
  unmerge_bills: false,
  split_bill: false,
  open_shift: false,
  close_shift: false,
};

/** Only `true` is a yes; a missing key or any other value is a no. */
export function normalizePermissions(raw: unknown): PosPermissions {
  const source = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  const result = { ...NO_PERMISSIONS };
  for (const key of Object.keys(NO_PERMISSIONS) as (keyof PosPermissions)[]) {
    result[key] = source[key] === true;
  }
  return result;
}

/** The discount box: the user may give discounts and the POS Profile has discounts switched on. */
export function canShowDiscount(
  permissions: PosPermissions | null,
  profileEnableDiscount: number | null | undefined
): boolean {
  return Boolean(permissions?.apply_discount) && profileEnableDiscount === 1;
}

/** What to show for a failed call: a translated line when the user may not do it, else the server's text. */
export function friendlyError(
  err: unknown,
  fallback: string,
  t: (key: string) => string
): string {
  if (isPermissionError(err)) return t('errors.not_permitted_billing');
  return parseFrappeError(err, fallback);
}

export async function getPosPermissions(): Promise<PosPermissions> {
  const res = await call.get<{ message?: unknown }>('ury.ury.api.pos_permissions.get_pos_permissions');
  return normalizePermissions(res?.message ?? res);
}
