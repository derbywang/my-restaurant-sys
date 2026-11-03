// Why `sync_order` refused a write. The server returns `{ status: 'Failure' }` and says why in a
// message (its title); the POS used to say "modified" whatever the reason.

const TITLES: Record<string, string> = {
  'order has been modified': 'errors.order_modified',
  'table occupied': 'errors.table_occupied',
  'invoice already billed': 'errors.order_already_billed',
};

function serverTitles(response: unknown): string[] {
  const raw = (response as { _server_messages?: unknown } | null | undefined)?._server_messages;
  if (typeof raw !== 'string') return [];
  try {
    const list = JSON.parse(raw);
    if (!Array.isArray(list)) return [];
    return list.flatMap((item) => {
      try {
        const title = JSON.parse(item)?.title;
        return typeof title === 'string' ? [title.trim().toLowerCase()] : [];
      } catch {
        return [];
      }
    });
  } catch {
    return [];
  }
}

/** The i18n key of the message to show for a refused write; `updating` picks the old default. */
export function syncFailureMessageKey(response: unknown, updating: boolean): string {
  for (const title of serverTitles(response)) {
    if (TITLES[title]) return TITLES[title];
  }
  return updating ? 'errors.order_modified' : 'errors.order_sync_failed';
}
