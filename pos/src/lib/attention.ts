export const ATTENTION_TYPES = ['pending_payment', 'table_occupied_long', 'kot_errors', 'unclosed_pos_session'] as const;

export interface AttentionItem {
  type: string;
  count?: number;
  message: string;
}

type Translate = (key: string, options?: { count?: number }) => string;

/** The text of one line of "needs attention": from the kind and the count, in the staff language. */
export function attentionMessage(item: AttentionItem, t: Translate): string {
  if (!(ATTENTION_TYPES as readonly string[]).includes(item.type)) return item.message;
  return t(`dashboard.attention.${item.type}`, { count: item.count ?? 0 });
}
