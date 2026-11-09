import { useEffect, useState } from 'react';
import { useConfigure } from '../../../context/ConfigureContext';
import { call } from '@ury/core';
import { SearchableSelect, Option } from '../../common/SearchableSelect';
import { Button } from '@ury/ui';
import { Plus, Trash2 } from 'lucide-react';
import type { PaymentKind } from '../../../context/ConfigureContext';

const DEFAULTS = ['Cash', 'Card'];

// Japan: cash plus the cashless methods the shop supports; each gets a settlement account
// (売掛金（…）) of its own when the setup runs.
const japanDefaults = (cash: string): { name: string; kind: PaymentKind }[] => [
  { name: cash, kind: 'cash' },
  { name: 'クレジットカード', kind: 'cashless' },
  { name: 'PayPay', kind: 'cashless' },
  { name: '楽天ペイ', kind: 'cashless' },
];

export function PaymentSection() {
  const { paymentMethods, addPaymentMethod, updatePaymentMethod, deletePaymentMethod, isJapan, country, cashMode } = useConfigure();
  // The cash Mode of Payment is "Cash" only on a site installed in English (「現金」 on a Japanese one)
  const cashName = cashMode || 'Cash';
  const [allModes, setAllModes] = useState<Option[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);

  useEffect(() => {
    call<any>('frappe.client.get_list', {
      doctype: 'Mode of Payment',
      fields: ['name'],
      limit: 100,
    })
      .then((res: any) => {
        const rows: { name: string }[] = res?.message ?? res ?? [];
        const names = rows.map((r: { name: string }) => r.name);
        const opts = names.map(n => ({ value: n, label: n }));
        setAllModes(opts);

        // Pre-select defaults that exist in the list and aren't already selected (not in Japan,
        // where the preset below is used)
        const currentNames = new Set(paymentMethods.map((m) => m.name));
        DEFAULTS.forEach((preset) => {
          const d = preset === 'Cash' ? cashName : preset;
          if (!isJapan && names.includes(d) && !currentNames.has(d)) {
            addPaymentMethod({ name: d });
          }
        });
      })
      .catch(() =>
        setFetchError('Could not load payment methods, check your connection.')
      )
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // The cash method starts as "Cash"; once the site's cash Mode of Payment is known it takes its name
  useEffect(() => {
    if (cashName === 'Cash') return;
    paymentMethods.forEach((m) => {
      if (m.name === 'Cash' && m.kind !== 'cashless') updatePaymentMethod(m.id, { name: cashName });
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cashName]);

  // Japan: preset the cashless methods once the country is known (nothing is added twice)
  useEffect(() => {
    if (!isJapan) return;
    // the first "Cash" is being renamed to the site's cash mode in the effect above
    const present = new Set(paymentMethods.map((m) => (m.name === 'Cash' ? cashName : m.name)));
    japanDefaults(cashName).forEach((d) => {
      if (!present.has(d.name)) addPaymentMethod(d);
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [country, cashName]);

  const handleAdd = () => {
    addPaymentMethod({ name: '', kind: 'cashless' });
  };

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        {paymentMethods.map((method) => (
          <div key={method.id} className="flex items-center gap-3">
            <div className="flex-1">
              <SearchableSelect
                id={`pm-${method.id}`}
                value={method.name}
                options={allModes}
                onChange={(_id, value) => updatePaymentMethod(method.id, { name: value })}
                placeholder="Select Mode of Payment"
                disabled={loading}
              />
            </div>
            <select
              aria-label="Type"
              value={method.kind ?? (method.name === 'Cash' ? 'cash' : 'cashless')}
              onChange={(e) => updatePaymentMethod(method.id, { kind: e.target.value as PaymentKind })}
              className="h-10 rounded-md border border-input bg-background px-2 text-sm shrink-0"
            >
              <option value="cash">{isJapan ? '現金' : 'Cash'}</option>
              <option value="cashless">{isJapan ? 'キャッシュレス' : 'Cashless'}</option>
            </select>
            {paymentMethods.length > 1 && (
              <Button
                type="button"
                variant="ghost"
                onClick={() => deletePaymentMethod(method.id)}
                className="text-red-500 hover:text-red-700 hover:bg-red-50 shrink-0 p-2 h-auto"
                title="Delete Method"
              >
                <Trash2 className="w-4 h-4" />
              </Button>
            )}
          </div>
        ))}
      </div>

      <p className="text-xs text-muted-foreground">
        {isJapan
          ? 'キャッシュレス（カード・QR決済など）は、精算会社ごとの「売掛金（…）」勘定が自動で作成されます。勘定科目名は後から変更できます。'
          : 'Cashless methods get a clearing account of their own, created automatically.'}
      </p>

      {fetchError && (
        <p className="text-xs font-medium text-red-600">{fetchError}</p>
      )}

      <Button
        type="button"
        variant="outline"
        onClick={handleAdd}
        className="w-full py-2.5 border-dashed border-primary text-primary hover:bg-primary/10 flex items-center justify-center gap-2 text-sm font-medium"
      >
        <Plus className="w-4 h-4" />
        Add Payment Method
      </Button>
    </div>
  );
}
