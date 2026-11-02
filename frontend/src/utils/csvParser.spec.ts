import { describe, expect, it } from 'vitest';
import { parseMenuCsv } from './csvParser';
import { normalizeMenuKind } from './menuKind';

describe('normalizeMenuKind', () => {
  it('keeps the three kinds, trimmed', () => {
    expect(normalizeMenuKind('食品')).toBe('食品');
    expect(normalizeMenuKind(' 酒類 ')).toBe('酒類');
    expect(normalizeMenuKind('非食品')).toBe('非食品');
  });

  it('is food when empty or unknown', () => {
    expect(normalizeMenuKind('')).toBe('食品');
    expect(normalizeMenuKind(undefined)).toBe('食品');
    expect(normalizeMenuKind('飲料')).toBe('食品');
  });
});

describe('parseMenuCsv kind column', () => {
  const header = '"Item","Item Name","Rate","Special Dish","Disabled","Course Icon","Course","種類"';

  it('reads 種類 from the template layout', () => {
    const rows = parseMenuCsv(
      [header, '"A","寿司",1000,0,0,"","Main Course","食品"', '"B","ビール",500,0,0,"","Beverages","酒類"', '"C","袋",5,0,0,"","Sides","非食品"'].join('\n')
    );
    expect(rows.map((r) => r.kind)).toEqual(['食品', '酒類', '非食品']);
  });

  it('defaults to 食品 when the column is missing or empty', () => {
    const noColumn = parseMenuCsv('"Item","Item Name","Rate","Course"\n"A","寿司",1000,"Main Course"');
    expect(noColumn[0].kind).toBe('食品');
    const empty = parseMenuCsv([header, '"A","寿司",1000,0,0,"","Main Course",""'].join('\n'));
    expect(empty[0].kind).toBe('食品');
  });

  it('reads 種類 from the simple name,course,price,kind layout', () => {
    const rows = parseMenuCsv('name,course,price,kind\nビール,Beverages,500,酒類');
    expect(rows[0]).toMatchObject({ name: 'ビール', price: 500, kind: '酒類' });
  });
});
