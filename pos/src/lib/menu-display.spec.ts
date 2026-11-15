import { describe, expect, it } from 'vitest';
import { shownCategories, shownItems } from './menu-display';

const item = (code: string, course: string, is_addon?: boolean) => ({ item: code, course, is_addon });

describe('what the register and the captain\'s screen show of the menu', () => {
  const items = [item('握り', '握り'), item('握り・大盛り', 'トッピング・追加', true), item('ビール', '飲み物'), item('ビール・氷', 'トッピング・追加', true), item('玉子', '握り', false)];

  it('a topping has no card, a search result or a count: only the dishes are shown', () => {
    expect(shownItems(items).map((i) => i.item)).toEqual(['握り', 'ビール', '玉子']);
  });

  it('an item without the mark is a dish (menus loaded by older code, aggregators)', () => {
    expect(shownItems([{ item: 'x' }, { item: 'y', is_addon: undefined }])).toHaveLength(2);
  });

  it('the course that has only toppings is not a tab; a course without items at all stays as it was', () => {
    const categories = [{ name: '握り' }, { name: '飲み物' }, { name: 'トッピング・追加' }, { name: 'まだ空の分類' }];
    expect(shownCategories(categories, items).map((c) => c.name)).toEqual(['握り', '飲み物', 'まだ空の分類']);
  });

  it('a course with dishes and toppings stays', () => {
    const mixed = [item('定食', '定食'), item('定食・大盛り', '定食', true)];
    expect(shownCategories([{ name: '定食' }], mixed).map((c) => c.name)).toEqual(['定食']);
  });
});
