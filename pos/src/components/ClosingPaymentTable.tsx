import React from 'react';
import { ClosingPaymentSummary } from '../lib/pos-closing-api';
import { Input } from '@ury/ui';
import { formatCurrency } from '@ury/core';
import { cn } from '@ury/ui';
import { t } from '../i18n';
import { usePOSStore } from '../store/pos-store';
import { paymentModeLabel } from '../lib/payment-change';
import { blockedYenKey, wholeYen } from '../lib/yen-input';

interface ClosingPaymentTableProps {
  rows: ClosingPaymentSummary[];
  /** Modes the cashier has explicitly entered a closing amount for (see Fix 2). */
  touchedModes: Set<string>;
  onChange: (modeOfPayment: string, closingAmount: number) => void;
}

const ClosingPaymentTable: React.FC<ClosingPaymentTableProps> = ({
  rows,
  touchedModes,
  onChange,
}) => {
  const paymentModeTypes = usePOSStore((state) => state.paymentModeTypes);

  const handleClosingAmountChange = (modeOfPayment: string, value: string) => {
    // Whole yen, never negative -- the HTML `min="0"` attribute alone does
    // not stop programmatic or pasted input.
    const closingAmount = wholeYen(value);
    onChange(modeOfPayment, closingAmount);
  };

  return (
    <div className="w-full overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-gray-300 bg-gray-50">
            <th className="text-left py-3 px-4 font-semibold text-gray-900">
              {t('pos_closing.col_mode')}
            </th>
            <th className="text-right py-3 px-4 font-semibold text-gray-900">
              {t('pos_closing.col_opening')}
            </th>
            <th className="text-right py-3 px-4 font-semibold text-gray-900">
              <span
                title={t('pos_closing.help_expected')}
                className="inline-flex items-center gap-1 cursor-help"
              >
                {t('pos_closing.col_expected')}
                <span
                  aria-hidden="true"
                  className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-gray-400 text-[10px] leading-none text-gray-500"
                >
                  i
                </span>
              </span>
            </th>
            <th className="text-center py-3 px-4 font-semibold text-gray-900">
              <span
                title={t('pos_closing.help_closing')}
                className="inline-flex items-center gap-1 cursor-help"
              >
                {t('pos_closing.col_closing')}
                <span
                  aria-hidden="true"
                  className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-gray-400 text-[10px] leading-none text-gray-500"
                >
                  i
                </span>
              </span>
            </th>
            <th className="text-right py-3 px-4 font-semibold text-gray-900">
              <span
                title={t('pos_closing.help_difference')}
                className="inline-flex items-center gap-1 cursor-help"
              >
                {t('pos_closing.col_difference')}
                <span
                  aria-hidden="true"
                  className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-gray-400 text-[10px] leading-none text-gray-500"
                >
                  i
                </span>
              </span>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            // Positive = overage (cashier has more than expected), negative
            // = shortage. Must match the sign convention used in the submit
            // payload built by POSClosingDialog.handleSubmit.
            const difference = row.closing_amount - row.expected_amount;
            const hasDifference = Math.abs(difference) > 0.001;
            const isTouched = touchedModes.has(row.mode_of_payment);

            return (
              <tr
                key={row.mode_of_payment}
                className={cn(
                  'border-b border-gray-200 hover:bg-gray-50 transition-colors',
                  !isTouched && 'bg-amber-50/60'
                )}
              >
                <td className="py-3 px-4 text-gray-900 font-medium">
                  {paymentModeLabel(row.mode_of_payment, paymentModeTypes, t('payment.cash'))}
                </td>
                <td className="py-3 px-4 text-right text-gray-700">
                  {formatCurrency(row.opening_amount)}
                </td>
                <td className="py-3 px-4 text-right text-gray-700">
                  {formatCurrency(row.expected_amount)}
                </td>
                <td className="py-3 px-4">
                  <Input
                    type="number"
                    min="0"
                    step="1"
                    value={row.closing_amount > 0 ? String(row.closing_amount) : ''}
                    onChange={(e) =>
                      handleClosingAmountChange(row.mode_of_payment, e.target.value)
                    }
                    placeholder="0"
                    onKeyDown={(e) => {
                      if (blockedYenKey(e.key)) e.preventDefault();
                    }}
                    onPaste={(e) => {
                      if (!/^\d*$/.test(e.clipboardData.getData('text'))) e.preventDefault();
                    }}
                    className={cn('w-full text-center', !isTouched && 'border-amber-400')}
                    size="sm"
                  />
                </td>
                <td
                  className={cn(
                    'py-3 px-4 text-right font-medium',
                    hasDifference ? 'text-red-600' : 'text-green-600'
                  )}
                >
                  {formatCurrency(difference)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

export default ClosingPaymentTable;
