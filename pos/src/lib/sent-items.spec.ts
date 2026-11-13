import { describe, expect, it } from 'vitest';

import { canClearOrder, canDecrease, canRemoveLine, noteIsLocked, noteLockedMessageKey, wouldEmptyASentOrder } from './sent-items';

const NEW_LINE = { quantity: 2 };
const SENT_LINE = { quantity: 2, sentQuantity: 2 };
const SENT_AND_ADDED = { quantity: 3, sentQuantity: 2 };

describe('who sees the minus and the trash can', () => {
  it('lets anyone change a line that was not sent yet', () => {
    expect(canDecrease(NEW_LINE, false)).toBe(true);
    expect(canRemoveLine(NEW_LINE, false)).toBe(true);
  });

  it('keeps a sent line as it is for someone who may not take dishes back', () => {
    expect(canDecrease(SENT_LINE, false)).toBe(false);
    expect(canRemoveLine(SENT_LINE, false)).toBe(false);
  });

  it('lets them take back only what they added after the order was sent', () => {
    expect(canDecrease(SENT_AND_ADDED, false)).toBe(true);
    expect(canDecrease({ quantity: 2, sentQuantity: 2 }, false)).toBe(false);
    expect(canRemoveLine(SENT_AND_ADDED, false)).toBe(false);
  });

  it('lets the cashier and the manager change every line', () => {
    expect(canDecrease(SENT_LINE, true)).toBe(true);
    expect(canRemoveLine(SENT_LINE, true)).toBe(true);
    expect(canDecrease(SENT_AND_ADDED, true)).toBe(true);
  });

  it('treats a line of zero sent dishes as not sent', () => {
    expect(canRemoveLine({ quantity: 1, sentQuantity: 0 }, false)).toBe(true);
  });
});

describe('emptying the order', () => {
  it('is for those who may take back what was sent, once something was sent', () => {
    expect(canClearOrder([SENT_LINE, NEW_LINE], false)).toBe(false);
    expect(canClearOrder([SENT_LINE, NEW_LINE], true)).toBe(true);
  });

  it('is open to anyone while nothing was sent', () => {
    expect(canClearOrder([NEW_LINE, { quantity: 1 }], false)).toBe(true);
    expect(canClearOrder([], false)).toBe(true);
  });
});

describe('the note of a line', () => {
  it('can be written on a line that was not sent yet', () => {
    expect(noteIsLocked(NEW_LINE)).toBe(false);
    expect(noteIsLocked({ sentQuantity: 0 })).toBe(false);
  });

  it('is locked once any of the line was sent, also when more was added after', () => {
    expect(noteIsLocked(SENT_LINE)).toBe(true);
    expect(noteIsLocked(SENT_AND_ADDED)).toBe(true);
  });

  it('is said to those who may take dishes back with how to change it, to the others without', () => {
    expect(noteLockedMessageKey(false)).toBe('cart.sent_note_locked');
    expect(noteLockedMessageKey(true)).toBe('cart.sent_note_locked_reducer');
  });
});

describe('wouldEmptyASentOrder', () => {
  const sentLine = (uniqueId: string, sentQuantity = 1) => ({ uniqueId, quantity: 1, sentQuantity });
  const newLine = (uniqueId: string) => ({ uniqueId, quantity: 1 });

  it('taking away the last line of an order that is with the kitchen would leave it empty', () => {
    expect(wouldEmptyASentOrder([sentLine('a')], 'a')).toBe(true);
  });

  it('taking away one of two lines does not', () => {
    expect(wouldEmptyASentOrder([sentLine('a'), sentLine('b')], 'a')).toBe(false);
  });

  it('taking away the last line of an order that was never sent is fine (nothing to take back from the kitchen)', () => {
    expect(wouldEmptyASentOrder([newLine('a')], 'a')).toBe(false);
  });

  it('a new line next to the sent one: taking away the sent one still leaves a line', () => {
    expect(wouldEmptyASentOrder([sentLine('a'), newLine('b')], 'a')).toBe(false);
  });

  it('emptying the whole cart of an order that is with the kitchen would leave it empty', () => {
    expect(wouldEmptyASentOrder([sentLine('a'), newLine('b')])).toBe(true);
  });

  it('an empty cart is not an order that is with the kitchen', () => {
    expect(wouldEmptyASentOrder([])).toBe(false);
  });
});
