import { describe, expect, it } from 'vitest';

import { mergeDetailRows } from './order-detail-rows';

const row = (over: Record<string, unknown> = {}) => ({
  name: 'r1',
  item_code: 'Burger',
  item_name: 'Burger',
  qty: 1,
  rate: 180,
  amount: 180,
  comment: '',
  ...over,
});

describe('mergeDetailRows (the order detail of the order list says what the edit screen and the receipt say)', () => {
  it('the rows of the same dish and note are one row: quantity and amount added', () => {
    const rows = mergeDetailRows([row(), row({ name: 'r2', qty: 2, amount: 360 })]);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ item_name: 'Burger', qty: 3, amount: 540, comment: '' });
  });

  it('a different note is another row; the order of the first appearance is kept', () => {
    const rows = mergeDetailRows([
      row({ qty: 3, amount: 540 }),
      row({ name: 'r2', item_code: 'Sake', item_name: 'Sake', qty: 1, rate: 500, amount: 500 }),
      row({ name: 'r3', qty: 2, amount: 360, comment: '辛さ控えめ' }),
      row({ name: 'r4', qty: 1, amount: 180 }),
    ]);
    expect(rows.map((r) => [r.item_name, r.qty, r.comment])).toEqual([
      ['Burger', 4, ''],
      ['Sake', 1, ''],
      ['Burger', 2, '辛さ控えめ'],
    ]);
  });

  it('a note of spaces only is no note', () => {
    expect(mergeDetailRows([row({ comment: '  ' }), row({ comment: '' })])).toHaveLength(1);
  });

  it('a missing note is no note (the server may send null)', () => {
    expect(mergeDetailRows([row({ comment: null }), row({ comment: undefined })])).toHaveLength(1);
  });

  it('rows without a dish code (an older answer) are joined by their name', () => {
    expect(mergeDetailRows([row({ item_code: undefined }), row({ item_code: undefined, qty: 2 })])).toHaveLength(1);
  });

  it('does not change the rows it is given', () => {
    const rows = [row(), row({ qty: 2 })];
    mergeDetailRows(rows);
    expect(rows[0].qty).toBe(1);
  });
});
