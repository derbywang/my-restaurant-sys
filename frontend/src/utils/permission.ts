/** What the admin pages may do with a DocType (the answer of `ury.ury.api.dashboard.get_module_permissions`). */
export interface ModulePermissions {
  create: boolean;
  write: boolean;
}

export const NO_MODULE_PERMISSIONS: ModulePermissions = { create: false, write: false };

/**
 * `{ create, write }` from the response of `get_module_permissions` (possibly wrapped in `message`).
 * Only `true` is a yes: an error or an unexpected shape is a no, so a button stays hidden.
 */
export function modulePermissionsFrom(response: unknown): ModulePermissions {
  const body = ((response as { message?: unknown } | null | undefined)?.message ?? response) as
    | { create?: unknown; write?: unknown }
    | null
    | undefined;
  return { create: body?.create === true, write: body?.write === true };
}
