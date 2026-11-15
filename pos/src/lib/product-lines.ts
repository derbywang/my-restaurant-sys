import type { MenuItem, OrderItem } from '../store/pos-store';

export interface Choice {
  selectedItem: MenuItem;
  basePrice: number;
  quantity: number;
  comment: string;
  addons: Array<{ id: string; name: string; price: number }>;
  /** The dish is already ordered and only toppings are added to it: the dish is not added again. */
  toppingsOnly: boolean;
}

/** May the dialog add now: a quantity, and a topping when only toppings are added. */
export function canAddChoice(quantity: number, addons: unknown[], toppingsOnly: boolean): boolean {
  if (Number.isNaN(quantity) || quantity <= 0) return false;
  return !toppingsOnly || addons.length > 0;
}

/** What the dialog shows as the total: the dish is left out when only toppings are added. */
export function choiceTotal(basePrice: number, addons: Array<{ price: number }>, quantity: number, toppingsOnly: boolean): number {
  const addonsTotal = addons.reduce((sum, addon) => sum + addon.price, 0);
  return ((toppingsOnly ? 0 : basePrice) + addonsTotal) * quantity;
}

/**
 * The lines the dialog of a dish puts in the order: the dish, then each topping with the same quantity (a topping is a line
 * of its own, named 「dish・topping」). With `toppingsOnly` only the toppings.
 */
export function linesToAdd(choice: Choice, menuItems: MenuItem[]): OrderItem[] {
  const lines: OrderItem[] = [];
  if (!choice.toppingsOnly) {
    lines.push({
      ...choice.selectedItem,
      quantity: choice.quantity,
      price: choice.basePrice,
      comment: choice.comment.trim() || undefined,
    });
  }
  for (const addon of choice.addons) {
    const menuAddon = menuItems.find((item) => item.item === addon.id);
    lines.push(
      menuAddon
        ? { ...menuAddon, quantity: choice.quantity, price: addon.price }
        : ({
            id: addon.id,
            name: addon.name,
            price: addon.price,
            quantity: choice.quantity,
            image: null,
            item: addon.id,
            item_name: addon.name,
            course: '',
            description: '',
            special_dish: 0 as 0 | 1,
            tax_rate: 0,
          } as OrderItem)
    );
  }
  return lines;
}
