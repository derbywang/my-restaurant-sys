// Pure helpers of the setup wizard: fiscal year dates and the texts that depend on the country.
// Dates are always year-month-day strings ("2026-04-01"); what the screen shows is built from them
// here, never from the system's date format.

// Month-day on which the fiscal year starts, by country (MM-DD). Not listed: January 1st.
const FISCAL_YEARS: Record<string, string> = {
  Afghanistan: '12-21',
  Australia: '07-01',
  Bangladesh: '07-01',
  'Costa Rica': '10-01',
  Egypt: '07-01',
  Ethiopia: '07-08',
  'Hong Kong': '04-01',
  India: '04-01',
  Iran: '06-23',
  Japan: '01-01',
  Kenya: '07-01',
  Malaysia: '07-01',
  Myanmar: '04-01',
  Nepal: '07-16',
  'New Zealand': '04-01',
  Pakistan: '07-01',
  Singapore: '04-01',
  'South Africa': '03-01',
  Thailand: '10-01',
  'United Kingdom': '04-01',
};

function pad(value: number): string {
  return String(value).padStart(2, '0');
}

function parseIso(iso: string): { year: number; month: number; day: number } | null {
  const match = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(iso);
  if (!match) return null;
  return { year: Number(match[1]), month: Number(match[2]), day: Number(match[3]) };
}

export function fiscalYearStart(country: string, year: number): string {
  return `${year}-${FISCAL_YEARS[country] || '01-01'}`;
}

/** The last day of the fiscal year that starts on `start`: one year later, minus a day. */
export function fiscalYearEnd(start: string): string {
  const parts = parseIso(start);
  if (!parts) return '';
  const end = new Date(Date.UTC(parts.year + 1, parts.month - 1, parts.day - 1));
  return `${end.getUTCFullYear()}-${pad(end.getUTCMonth() + 1)}-${pad(end.getUTCDate())}`;
}

/** "2026-4-1" -> "2026-04-01". */
export function formatIsoDate(iso: string): string {
  const parts = parseIso(iso);
  return parts ? `${parts.year}-${pad(parts.month)}-${pad(parts.day)}` : iso;
}

/** "2026-04-01" -> "2026年4月1日". */
export function formatJapaneseDate(iso: string): string {
  const parts = parseIso(iso);
  return parts ? `${parts.year}年${parts.month}月${parts.day}日` : '';
}

/** "2026年4月1日 〜 2027年3月31日" */
export function fiscalYearLabel(start: string): string {
  const end = fiscalYearEnd(start);
  if (!end) return '';
  return `${formatJapaneseDate(start)} 〜 ${formatJapaneseDate(end)}`;
}

export function priceColumnLabel(currency?: string | null): string {
  return currency ? `Price (${currency})` : 'Price';
}

export function paymentHint(isJapan: boolean): string {
  return isJapan
    ? 'How your customers will pay. Cash is added by default — add credit cards, PayPay or other methods your restaurant accepts.'
    : 'How your customers will pay. Cash is added by default — add Card or other methods your restaurant accepts.';
}

/** What the price box holds: an empty box is no price yet (not 0), so the cashier can clear it. */
export function parsePriceInput(raw: string): number | null {
  const text = raw.trim();
  if (text === '') return null;
  const value = Number(text);
  return Number.isFinite(value) && value >= 0 ? value : null;
}

export function priceInputValue(price: number | null | undefined): string {
  return price === null || price === undefined ? '' : String(price);
}

/** The items that have a name but no price. A price of 0 is a price (a free item). */
export function missingPriceNames(items: { name: string; price: number | null }[]): string[] {
  return items.filter((item) => item.name.trim() !== '' && item.price === null).map((item) => item.name.trim());
}

export function missingPriceMessage(names: string[]): string {
  return `Enter a price for: ${names.join(', ')} (0 is allowed for a free item).`;
}
