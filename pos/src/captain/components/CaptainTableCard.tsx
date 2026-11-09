import type { ReactNode } from 'react';
import { Bell, User, Users } from 'lucide-react';
import { cn } from '@ury/ui';
import { Badge } from '@ury/ui';
import { elapsedMinutes, formatCurrency } from '@ury/core';
import { t } from '../../i18n';
import type { Table } from '../../lib/table-api';
import type { ActiveTableOrder } from '../lib/captain-table-api';
import type { CardState } from '../../lib/service-requests';
import { waitingBillsLabel, type WaitingBills } from '../../lib/table-bills';

export type CaptainTableOwnership = 'free' | 'mine' | 'other' | 'occupied-unknown';

export interface CaptainTableCardProps {
  table: Table;
  order?: ActiveTableOrder;
  ownership: CaptainTableOwnership;
  ownerName?: string;
  /** Names of other tables merged into this one's cluster (excludes `table.name` itself). */
  mergePartners?: string[];
  onTap: () => void;
  /** The self-order button of the table (a SelfOrderToggle), when the branch uses self ordering. */
  selfOrderSlot?: ReactNode;
  /** The guests' 「お会計」 call of the table (null: none): the same as on the register's card (bell, minutes, 確認済み, red after 3 minutes). */
  billCall?: CardState | null;
  /** Printed bills of this table not paid yet: a small mark 「会計待ち ¥…」; the table itself is 空席 or 使用中 by its occupancy. */
  waitingBills?: WaitingBills | null;
}

const elapsedLabel = (timestamp: string | null): string | null => {
  const minutes = elapsedMinutes(timestamp);
  if (minutes === null) return null;
  if (minutes < 1) return t('captain.elapsed_just_now');
  if (minutes < 60) return t('captain.elapsed_minutes', { minutes });
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder
    ? t('captain.elapsed_hours_minutes', { hours, minutes: remainder })
    : t('captain.elapsed_hours', { hours });
};

/**
 * Large, touch-friendly table card for the Captain's mobile "Tables" home
 * screen. Deliberately no cashier-oriented chrome (no print/preview/payment
 * affordances) — a card here only communicates status and is a single tap
 * target, per PLAN.md §5/§6.
 *
 * Visual states implemented: Free, Mine, Occupied-by-another-Captain,
 * Billed/locked, Merged. "Attention" is intentionally not implemented — see
 * report; the data it would need (a time threshold) isn't exposed by
 * `get_captain_context()` today.
 */
const CaptainTableCard = ({
  table,
  order,
  ownership,
  ownerName,
  mergePartners,
  onTap,
  selfOrderSlot,
  billCall = null,
  waitingBills = null,
}: CaptainTableCardProps) => {
  const isOccupied = table.occupied === 1;
  const hasMergePartners = Boolean(mergePartners && mergePartners.length > 0);
  const elapsed = isOccupied ? elapsedLabel(table.latest_invoice_time) : null;

  // the state of the card is the occupancy of the table (空席 / 使用中); a bill waiting for the payment is a mark
  const colorClasses =
    ownership === 'mine'
      ? 'border-sky-400 bg-sky-50 text-sky-900'
      : ownership === 'free'
        ? 'border-emerald-300 bg-emerald-50 text-emerald-900'
        : 'border-amber-400 bg-amber-50 text-amber-900';

  const statusLabel =
    ownership === 'mine'
      ? t('captain.status_mine')
      : ownership === 'free'
        ? t('captain.status_free')
        : ownerName
          ? ownerName
          : t('captain.status_occupied');

  const statusBadgeVariant = ownership === 'mine' ? 'info' : ownership === 'free' ? 'success' : 'warning';

  return (
    <div
      className={cn(
        'flex flex-col rounded-xl border-2',
        colorClasses,
        billCall && (billCall.late ? 'ring-4 ring-red-500' : billCall.quiet ? 'ring-2 ring-amber-400' : 'ring-4 ring-amber-500')
      )}
    >
    <button
      type="button"
      onClick={onTap}
      className="flex min-h-[7.5rem] flex-1 flex-col items-stretch p-3 text-left transition-all active:scale-[0.98]"
    >
      {billCall && (
        <div
          data-testid="bill-call"
          className={cn(
            'mb-2 flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-semibold',
            billCall.late ? 'bg-red-100 text-red-800' : 'bg-amber-100 text-amber-900'
          )}
        >
          <Bell className={cn('h-4 w-4 shrink-0', !billCall.quiet && 'animate-bounce')} />
          <span>{t('service_request.call_bill')}</span>
          <span className="font-medium">{t('service_request.minutes', { minutes: billCall.minutes })}</span>
          {billCall.quiet && (
            <span className="ml-auto rounded bg-white/70 px-1.5 py-0.5 font-medium">{t('service_request.acknowledged')}</span>
          )}
        </div>
      )}
      <div className="flex items-start justify-between gap-2">
        <span className="min-w-0 break-words text-lg font-bold" title={table.name}>
          {table.name}
        </span>
      </div>

      {hasMergePartners && (
        <span
          className="mt-0.5 truncate text-xs font-medium opacity-80"
          title={t('captain.merged_with', { tables: mergePartners!.join(', ') })}
        >
          + {mergePartners!.join(', ')}
        </span>
      )}

      <div className="mt-2 flex flex-1 flex-col justify-end gap-1.5">
        <Badge variant={statusBadgeVariant} size="sm" className="w-fit truncate max-w-full">
          {statusLabel}
        </Badge>

        {waitingBills && (
          <Badge variant="secondary" size="sm" data-testid="bills-waiting" className="w-fit truncate max-w-full">
            {waitingBillsLabel(waitingBills, formatCurrency, (key, params) => t(key, params))}
          </Badge>
        )}

        {isOccupied && ownership !== 'mine' && ownerName && (
          <span className="flex items-center gap-1 truncate text-xs font-medium opacity-80">
            <User className="h-3 w-3 shrink-0" />
            {ownerName}
          </span>
        )}

        {isOccupied && (elapsed || typeof order?.grandTotal === 'number') && (
          <div className="flex items-center justify-between text-xs font-medium opacity-80">
            <span>{elapsed ?? '—'}</span>
            {typeof order?.grandTotal === 'number' && (
              <span>{formatCurrency(order.grandTotal)}</span>
            )}
          </div>
        )}

        {typeof table.no_of_seats === 'number' && (
          <span className="flex items-center gap-1 text-xs opacity-70">
            <Users className="h-3 w-3" />
            {table.no_of_seats}
          </span>
        )}
      </div>
    </button>
    {selfOrderSlot && <div className="px-3 pb-3">{selfOrderSlot}</div>}
    </div>
  );
};

export default CaptainTableCard;
