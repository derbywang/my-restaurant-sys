import { describe, expect, it } from 'vitest';
import { canAddChoice, choiceTotal, linesToAdd } from './product-lines';

const main = { id: '握り', item: '握り', name: '握り', item_name: '握り', price: 1000, image: null, course: '握り' } as never;
const menu = [
  { id: '握り・大盛り', item: '握り・大盛り', name: '握り・大盛り', item_name: '握り・大盛り', price: 100, image: null, course: 'トッピング・追加' },
] as never[];
const big = { id: '握り・大盛り', name: '握り・大盛り', price: 100 };
const miso = { id: '握り・味噌汁', name: '握り・味噌汁', price: 150 };

describe('the lines the dialog of a dish puts in the order', () => {
  it('the dish, then each topping with the same quantity (a topping is a line of its own)', () => {
    const lines = linesToAdd({ selectedItem: main, basePrice: 1000, quantity: 2, comment: ' わさび抜き ', addons: [big, miso], toppingsOnly: false }, menu);
    expect(lines.map((l) => [l.item, l.quantity, l.price, l.comment])).toEqual([
      ['握り', 2, 1000, 'わさび抜き'],
      ['握り・大盛り', 2, 100, undefined],
      ['握り・味噌汁', 2, 150, undefined],
    ]);
  });

  it('only the toppings when the cashier adds a topping to a dish already ordered (the dish is not added again)', () => {
    const lines = linesToAdd({ selectedItem: main, basePrice: 1000, quantity: 1, comment: '', addons: [big], toppingsOnly: true }, menu);
    expect(lines.map((l) => [l.item, l.quantity])).toEqual([['握り・大盛り', 1]]);
  });

  it('a topping that is not in the menu list is still a line (name and price from the dialog)', () => {
    const lines = linesToAdd({ selectedItem: main, basePrice: 1000, quantity: 1, comment: '', addons: [miso], toppingsOnly: true }, menu);
    expect(lines.map((l) => [l.item, l.item_name, l.price])).toEqual([['握り・味噌汁', '握り・味噌汁', 150]]);
  });

  it('toppings only needs a topping; a dish needs a quantity', () => {
    expect(canAddChoice(1, [], true)).toBe(false);
    expect(canAddChoice(1, [big], true)).toBe(true);
    expect(canAddChoice(0, [big], true)).toBe(false);
    expect(canAddChoice(1, [], false)).toBe(true);
    expect(canAddChoice(Number.NaN, [], false)).toBe(false);
  });

  it('the total of the dialog leaves the dish out when only toppings are added', () => {
    expect(choiceTotal(1000, [big, miso], 2, false)).toBe(2500);
    expect(choiceTotal(1000, [big, miso], 2, true)).toBe(500);
  });
});
