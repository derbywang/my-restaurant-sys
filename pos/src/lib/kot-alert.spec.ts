import { describe, expect, it } from 'vitest';
import en from '../i18n/locales/en.json';
import fr from '../i18n/locales/fr.json';
import ja from '../i18n/locales/ja.json';
import ko from '../i18n/locales/ko.json';
import zh from '../i18n/locales/zh.json';
import { kotAlertMessage, createAlertDedupe } from './kot-alert';

const t = (key: string, params?: Record<string, string | number>) =>
  `${key}${params ? JSON.stringify(params) : ''}`;

describe('kotAlertMessage', () => {
  it('shows a message the server wrote', () => {
    expect(kotAlertMessage({ message: 'Kitchen is on fire' }, t)).toBe('Kitchen is on fire');
  });

  it('names the table of a self-order whose ticket could not be made', () => {
    expect(kotAlertMessage({ kind: 'self_order', table: 'T-01', invoice: 'INV-1' }, t)).toBe(
      'kot_alert.self_order_table{"table":"T-01"}'
    );
    expect(kotAlertMessage({ kind: 'self_order' }, t)).toBe('kot_alert.self_order');
  });

  it('names the dishes that no kitchen makes', () => {
    expect(kotAlertMessage({ kind: 'no_kitchen', items: ['Sake', 'Beer'], invoice: 'INV-1' }, t)).toBe(
      'kot_alert.no_kitchen{"items":"Sake, Beer"}'
    );
    expect(kotAlertMessage({ kind: 'no_kitchen', items: [], invoice: 'INV-1' }, t)).toBe(
      'kot_alert.generic_invoice{"invoice":"INV-1"}'
    );
  });

  it('names the order of any other failed ticket, or just says so', () => {
    expect(kotAlertMessage({ kot: 'KOT-1', invoice: 'INV-1' }, t)).toBe('kot_alert.generic_invoice{"invoice":"INV-1"}');
    expect(kotAlertMessage({}, t)).toBe('kot_alert.generic');
    expect(kotAlertMessage(null, t)).toBe('kot_alert.generic');
  });

  it('has its lines in every staff language', () => {
    for (const locale of [ja, zh, ko, en, fr]) {
      const lines = (locale as unknown as { kot_alert: Record<string, string> }).kot_alert;
      for (const key of ['self_order', 'self_order_table', 'no_kitchen', 'generic', 'generic_invoice']) {
        expect(lines[key], key).toBeTruthy();
      }
      expect(lines.self_order_table).toContain('{{table}}');
      expect(lines.generic_invoice).toContain('{{invoice}}');
      expect(lines.no_kitchen).toContain('{{items}}');
    }
  });
});

describe('createAlertDedupe', () => {
  const payload = { kind: 'no_kitchen', invoice: 'INV-1', items: ['Sake'], production: 'A' };

  it('lets the same alert through once, although it comes on the channel of every production unit', () => {
    const seen = createAlertDedupe(5000);
    expect(seen(payload, 1000)).toBe(true);
    expect(seen({ ...payload, production: 'B' }, 1001)).toBe(false);
    expect(seen({ ...payload, production: 'C' }, 1002)).toBe(false);
  });

  it('lets a different order, other dishes, or the same alert much later through', () => {
    const seen = createAlertDedupe(5000);
    expect(seen(payload, 1000)).toBe(true);
    expect(seen({ ...payload, invoice: 'INV-2' }, 1001)).toBe(true);
    expect(seen({ ...payload, items: ['Beer'] }, 1002)).toBe(true);
    expect(seen(payload, 7000)).toBe(true);
  });
});
