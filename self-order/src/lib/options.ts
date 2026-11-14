// The dialog of a dish: grades (variants) and toppings. Pure functions, so that they can be tested.
import type { Grade, MenuItem, OptionItem, ProductInfo } from './api'
import type { CartAddon } from './cart'

/** The grades the dialog offers: the variants of the dish, or the dish itself (with its toppings) when it has none. */
export function gradesOf(product: ProductInfo): Grade[] {
  if (product.variants.length > 0) return product.variants
  return [
    {
      item_code: product.item_code,
      item_name: product.item_name,
      image: product.image,
      price_incl_tax: product.price_incl_tax,
      age_check: product.age_check,
      addons: product.addons,
    },
  ]
}

/** The grade the dialog starts with: the dish whose card was touched, else the first. */
export function initialGrade(product: ProductInfo, requested: string): Grade {
  const grades = gradesOf(product)
  return grades.find((g) => g.item_code === requested) ?? grades[0]
}

/** The toppings still ticked after another grade was chosen: those the new grade has too (matched by their label). */
export function carryOverAddons(ticked: readonly OptionItem[], offered: readonly OptionItem[]): OptionItem[] {
  const labels = new Set(ticked.map((a) => a.label ?? a.item_name))
  return offered.filter((a) => labels.has(a.label ?? a.item_name))
}

/** What the dialog comes to with the tax: the grade and the toppings, each as many as asked. */
export function subtotal(grade: OptionItem, addons: readonly OptionItem[], qty: number): number {
  if (!(qty > 0)) return 0
  return (grade.price_incl_tax + addons.reduce((sum, a) => sum + a.price_incl_tax, 0)) * qty
}

/** The guest is asked 「20歳以上ですか？」 when the grade or a topping is alcohol. */
export function needsAgeQuestion(grade: OptionItem, addons: readonly OptionItem[]): boolean {
  return grade.age_check || addons.some((a) => a.age_check)
}

/** The grade as a dish of the cart: the course and the image are those of the card it was chosen from. */
export function cartMain(card: MenuItem, grade: OptionItem): MenuItem {
  return {
    ...card,
    item: grade.item_code,
    item_name: grade.item_name,
    price_incl_tax: grade.price_incl_tax,
    age_check: grade.age_check,
    has_options: undefined,
    price_from: undefined,
  }
}

export function cartAddon(option: OptionItem): CartAddon {
  return {
    item: option.item_code,
    item_name: option.item_name,
    label: option.label ?? option.item_name,
    price_incl_tax: option.price_incl_tax,
    age_check: option.age_check,
  }
}

/** The price on a card of the grid: the lowest of the group, and whether to write the 〜 after it. */
export function cardPrice(item: MenuItem): { amount: number; from: boolean } {
  return { amount: item.price_incl_tax, from: Boolean(item.price_from) }
}
