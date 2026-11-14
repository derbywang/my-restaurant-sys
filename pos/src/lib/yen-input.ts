/** Yen has no decimals: the amounts typed on the opening and closing screens are whole numbers. */
export function wholeYen(value: string): number {
  const parsed = parseFloat(value);
  return Number.isFinite(parsed) ? Math.max(0, Math.floor(parsed)) : 0;
}

/** Keys that would make a decimal, a sign or an exponent in a number input. */
export function blockedYenKey(key: string): boolean {
  return ['.', ',', '-', '+', 'e', 'E', 'Minus'].includes(key);
}
