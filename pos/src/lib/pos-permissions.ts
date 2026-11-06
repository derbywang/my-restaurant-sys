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
  /** Take back a dish that already went to the kitchen (cashier, manager; not a captain). */
  reduce_sent_items: boolean;
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
  reduce_sent_items: false,
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

/**
 * Someone who takes orders and does nothing at the register (a waiter): she lands on the waiter screen (/order)
 * after login. Decided by what the server allows, never by a role name.
 */
export function isWaiterOnly(permissions: PosPermissions | null): boolean {
  return Boolean(
    permissions &&
      permissions.take_orders &&
      !permissions.settle_payment &&
      !permissions.open_shift &&
      !permissions.close_shift
  );
}

/** The menu of the register offers the waiter screen to everyone who takes orders there (a cashier, a manager). */
export function showsWaiterScreenLink(permissions: PosPermissions | null): boolean {
  return Boolean(permissions?.take_orders) && !isWaiterOnly(permissions);
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

/** What to show when an order cannot be opened: a translated line for a refusal (another store, another room). */
export function openOrderError(err: unknown, fallback: string, t: (key: string) => string): string {
  if (isPermissionError(err)) return t('errors.not_permitted_order');
  return parseFrappeError(err, fallback);
}

export async function getPosPermissions(): Promise<PosPermissions> {
  const res = await call.get<{ message?: unknown }>('ury.ury.api.pos_permissions.get_pos_permissions');
  return normalizePermissions(res?.message ?? res);
}
