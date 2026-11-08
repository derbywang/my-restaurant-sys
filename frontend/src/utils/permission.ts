/**
 * The answer of `frappe.client.has_permission` ({ has_permission: boolean }, possibly wrapped in `message`).
 * Only `true` is a yes: anything else (an error, an unexpected shape) is a no, so a button stays hidden.
 */
export function answerIsYes(response: unknown): boolean {
  const body = (response as { message?: unknown } | null | undefined)?.message ?? response;
  return (body as { has_permission?: unknown } | null | undefined)?.has_permission === true;
}
