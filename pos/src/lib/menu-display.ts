/**
 * What the register and the captain's screen show of the menu. A topping (an item that another item lists in its dialog,
 * `is_addon`) has no card, no search result and no count: it is chosen in the dialog of its dish. It stays in the store's
 * list because that dialog needs its name and price.
 */
export function shownItems<T extends { is_addon?: boolean | 0 | 1 }>(items: T[]): T[] {
  return items.filter((item) => !item.is_addon);
}

/** The course tabs: a course that has only toppings is not a tab (a course with no items at all is left as it was). */
export function shownCategories<C extends { name: string }>(
  categories: C[],
  items: Array<{ course?: string; is_addon?: boolean | 0 | 1 }>
): C[] {
  return categories.filter((category) => {
    const inCourse = items.filter((item) => item.course === category.name);
    return inCourse.length === 0 || inCourse.some((item) => !item.is_addon);
  });
}
