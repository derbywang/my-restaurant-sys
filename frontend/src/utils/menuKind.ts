/** 種類 of a menu item on a Japanese site; it decides the item group and so the consumption tax. */
export const MENU_KINDS = ['食品', '酒類', '非食品'] as const;
export type MenuKind = (typeof MENU_KINDS)[number];

export function normalizeMenuKind(value: string | null | undefined): MenuKind {
  const kind = (value ?? '').trim();
  return (MENU_KINDS as readonly string[]).includes(kind) ? (kind as MenuKind) : '食品';
}
