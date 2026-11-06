// Dishes that already went to the kitchen. Taking one back needs the permission the server gives
// (`reduce_sent_items`: the POS Profile allows it and the user may cancel POS Invoices); adding
// dishes, and taking back what was added after the order was sent, is open to everyone.
// This only decides what the screen offers; `sync_order` refuses the change on the server.

export interface SentLine {
  quantity: number;
  /** The quantity the server had when the order was loaded; missing for a line added in this session. */
  sentQuantity?: number;
}

const sent = (line: SentLine): number => line.sentQuantity ?? 0;

/** The minus button: below what was sent only if the user may take dishes back. */
export function canDecrease(line: SentLine, mayTakeBack: boolean): boolean {
  return mayTakeBack || line.quantity > sent(line);
}

/** The trash can: a line with sent dishes goes only if the user may take dishes back. */
export function canRemoveLine(line: SentLine, mayTakeBack: boolean): boolean {
  return mayTakeBack || sent(line) <= 0;
}

/** Emptying the whole order would take the sent dishes back too. */
export function canClearOrder(lines: SentLine[], mayTakeBack: boolean): boolean {
  return mayTakeBack || lines.every((line) => sent(line) <= 0);
}

/**
 * The note of a line that has dishes with the kitchen cannot be changed: the kitchen is told about quantities only, so a
 * changed note would show on the screen and never reach the kitchen. `sync_order` refuses it too ("Sent note locked").
 */
export function noteIsLocked(line: { quantity?: number; sentQuantity?: number }): boolean {
  return (line.sentQuantity ?? 0) > 0;
}

/** The i18n key of what is said when the note of a sent line is tapped. Those who may take dishes back are also told how. */
export function noteLockedMessageKey(mayTakeBack: boolean): string {
  return mayTakeBack ? 'cart.sent_note_locked_reducer' : 'cart.sent_note_locked';
}
