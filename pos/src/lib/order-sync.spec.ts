import { describe, expect, it } from 'vitest';

import { refusedNoteChange, refusedTakingBack, syncFailureMessageKey } from './order-sync';

const withTitle = (title: string) => ({
  message: { status: 'Failure' },
  _server_messages: JSON.stringify([JSON.stringify({ title, message: 'x', indicator: 'red' })]),
});

describe('syncFailureMessageKey', () => {
  it('says the order was modified when the server says so', () => {
    expect(syncFailureMessageKey(withTitle('Order has been modified'), true)).toBe('errors.order_modified');
  });

  it('says the table is taken when the server says so (the title has a trailing space on the server)', () => {
    expect(syncFailureMessageKey(withTitle('Table occupied '), false)).toBe('errors.table_occupied');
  });

  it('says the order was already billed when the server says so', () => {
    expect(syncFailureMessageKey(withTitle('Invoice Already Billed'), true)).toBe('errors.order_already_billed');
  });

  it('falls back to the old texts when the server gave no reason', () => {
    expect(syncFailureMessageKey({ message: { status: 'Failure' } }, true)).toBe('errors.order_modified');
    expect(syncFailureMessageKey({ message: { status: 'Failure' } }, false)).toBe('errors.order_sync_failed');
    expect(syncFailureMessageKey(undefined, false)).toBe('errors.order_sync_failed');
  });

  it('is not fooled by a broken or unknown message', () => {
    expect(syncFailureMessageKey({ _server_messages: 'not json' }, false)).toBe('errors.order_sync_failed');
    expect(syncFailureMessageKey(withTitle('Something else'), false)).toBe('errors.order_sync_failed');
  });
});

describe('refusedTakingBack', () => {
  it('knows the server refused to take a sent dish back (it throws, with that title)', () => {
    expect(refusedTakingBack(withTitle('Reduce not permitted'))).toBe(true);
  });

  it('is not fooled by other refusals or by something that is not a server answer', () => {
    expect(refusedTakingBack(withTitle('Table occupied '))).toBe(false);
    expect(refusedTakingBack(new Error('x'))).toBe(false);
    expect(refusedTakingBack(undefined)).toBe(false);
  });
});

describe('refusedNoteChange', () => {
  it('knows the server refused to change the note of a sent dish', () => {
    expect(refusedNoteChange(withTitle('Sent note locked'))).toBe(true);
  });

  it('is not fooled by the other refusal about sent dishes or by something that is not a server answer', () => {
    expect(refusedNoteChange(withTitle('Reduce not permitted'))).toBe(false);
    expect(refusedNoteChange(new Error('x'))).toBe(false);
  });
});
