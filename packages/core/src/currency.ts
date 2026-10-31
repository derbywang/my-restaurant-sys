type BootDoc = { doctype?: string; name?: string; default_currency?: string };
type FrappeBoot = {
  sysdefaults?: { currency?: string; company?: string };
  docs?: BootDoc[];
};

let override: string | undefined;

/**
 * Pin the currency used by the formatters, e.g. from the POS Profile or an
 * API response. Pass nothing to go back to the server default.
 */
export function setCurrency(code?: string | null): void {
  override = code ? code.toUpperCase() : undefined;
}

/**
 * ISO code of the currency to display amounts in, taken from the server:
 * an explicit `setCurrency()` value, else `frappe.boot.sysdefaults.currency`
 * (system default), else the default company's `default_currency`.
 * Returns undefined when none is available (guest pages have no boot data);
 * the formatters then show a plain number rather than guess a currency.
 */
export function getCurrency(): string | undefined {
  if (override) return override;

  const boot = (window as { frappe?: { boot?: FrappeBoot } }).frappe?.boot;
  const fromDefaults = boot?.sysdefaults?.currency;
  if (fromDefaults) return fromDefaults;

  const companies = (boot?.docs ?? []).filter((doc) => doc.doctype === ':Company');
  const company = companies.find((doc) => doc.name === boot?.sysdefaults?.company) ?? companies[0];
  return company?.default_currency || undefined;
}
