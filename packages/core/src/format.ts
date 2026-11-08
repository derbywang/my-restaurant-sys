import { getCurrency } from './currency';
import { getActiveLanguage } from './i18n';

const formatters = new Map<string, Intl.NumberFormat>();

function numberFormat(compact: boolean, currency: string | undefined): Intl.NumberFormat {
  const locale = getActiveLanguage();
  const key = `${locale}|${currency ?? ''}|${compact}`;
  let formatter = formatters.get(key);
  if (!formatter) {
    // With a currency, the minor-unit digits come from the currency itself
    // (JPY: none, USD: two); only the plain-number fallback needs a cap.
    const options: Intl.NumberFormatOptions = compact
      ? { notation: 'compact', maximumFractionDigits: 1 }
      : currency
        ? {}
        : { maximumFractionDigits: 2 };
    try {
      formatter = new Intl.NumberFormat(
        locale,
        currency ? { ...options, style: 'currency', currency, currencyDisplay: 'narrowSymbol' } : options
      );
    } catch {
      // unknown currency code: show the plain number instead of failing
      formatter = new Intl.NumberFormat(locale, options);
    }
    formatters.set(key, formatter);
  }
  return formatter;
}

const finite = (amount: number): number => (typeof amount === 'number' && Number.isFinite(amount) ? amount : 0);

/**
 * Formats an amount in the server's currency (see `getCurrency`) using the
 * active UI language, e.g. "¥1,235" (JPY has no minor unit), "$1,234.50".
 * Without a known currency only the number is formatted.
 */
export function formatCurrency(amount: number, currency?: string): string {
  return numberFormat(false, typeof currency === 'string' ? currency : getCurrency()).format(finite(amount));
}

export function flt(v: number | string | null | undefined, decimals: number = 2): number {
  if (v == null || v === '') return 0;
  const num = typeof v === 'number' ? v : parseFloat(v as string);
  if (isNaN(num)) return 0;
  if (decimals != null) {
    const mult = Math.pow(10, decimals);
    const isNegative = num < 0;
    const absNum = Math.abs(num);
    const n = +(absNum * mult).toFixed(8);
    const rounded = Math.round(n) / mult;
    return isNegative ? -rounded : rounded;
  }
  return num;
}

/**
 * Compact currency for chart axes/labels, following the UI language:
 * 600000 -> "¥600K" (en) / "￥60万" (ja), 8200 -> "¥8.2K" (en).
 */
export function formatCompactCurrency(amount: number, currency?: string): string {
  return numberFormat(true, typeof currency === 'string' ? currency : getCurrency()).format(finite(amount));
}

/**
 * A date and time as the server sends it ("2026-11-07 20:24:24.397245", or with a T) as a local Date.
 * Read by hand: Safari does not parse the space-separated form with `new Date(string)`. A bare time of day (the
 * old Time field) has no date and gives null.
 */
export const parseServerDatetime = (value: string | null | undefined): Date | null => {
  if (!value) return null;
  const match = value.trim().match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?$/);
  if (!match) return null;
  const [year, month, day, hour, minute, second] = match.slice(1).map((part) => Number(part ?? 0));
  const date = new Date(year, month - 1, day, hour, minute, second);
  const valid =
    date.getFullYear() === year &&
    date.getMonth() === month - 1 &&
    date.getDate() === day &&
    date.getHours() === hour &&
    date.getMinutes() === minute;
  return valid ? date : null;
};

/** Whole minutes since a server date and time (never negative: the tablet's clock may be a little behind). */
export const elapsedMinutes = (value: string | null | undefined, now: number = Date.now()): number | null => {
  const started = parseServerDatetime(value);
  if (!started) return null;
  return Math.max(0, Math.floor((now - started.getTime()) / 60000));
};

export const formatInvoiceTime = (timestamp: string | null) => {
    if (!timestamp) return 'No bill activity yet';

    const parsedDate = parseServerDatetime(timestamp) ?? new Date(timestamp);
    if (!Number.isNaN(parsedDate.getTime())) {
      const now = new Date();
      const sameDay =
        parsedDate.getFullYear() === now.getFullYear() &&
        parsedDate.getMonth() === now.getMonth() &&
        parsedDate.getDate() === now.getDate();
      // a table that has been open since another day shows the day as well
      return parsedDate.toLocaleString(
        undefined,
        sameDay
          ? { hour: 'numeric', minute: 'numeric' }
          : { month: 'numeric', day: 'numeric', hour: 'numeric', minute: 'numeric' },
      );
    }

    const timeOnlyMatch = timestamp.match(/^(\d{1,2}):(\d{2}):(\d{2})(?:\.(\d+))?$/);
    if (timeOnlyMatch) {
      const [, hours, minutes, seconds] = timeOnlyMatch;
      const date = new Date();
      date.setHours(Number(hours), Number(minutes), Number(seconds), 0);
      const formatted = date.toLocaleTimeString(undefined, {
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      });
      if (/^\d{1,2}:\d{2}$/.test(formatted)) {
        return formatted;
      }
      return `${hours.padStart(2, '0')}:${minutes.padStart(2, '0')}`;
    }

    return timestamp;
  };