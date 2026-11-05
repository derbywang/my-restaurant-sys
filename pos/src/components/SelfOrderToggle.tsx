import { QrCode } from 'lucide-react';
import { cn } from '@ury/ui';
import { t } from '../i18n';
import {
  minutesOpen,
  selfOrderAction,
  type SelfOrderTables,
} from '../lib/self-order-tables';

interface SelfOrderToggleProps {
  state: SelfOrderTables;
  table: string;
  isTakeAway: boolean;
  now: number;
  busy: string | null;
  onToggle: (table: string, action: 'start' | 'stop') => void;
  className?: string;
}

/**
 * The button of a table that lets the guests order with the QR code on it ("セルフオーダー開始 / 停止"),
 * with how long the table has been open. Shows nothing when the branch does not use self ordering.
 */
const SelfOrderToggle = ({ state, table, isTakeAway, now, busy, onToggle, className }: SelfOrderToggleProps) => {
  const action = selfOrderAction(state, table, { isTakeAway });
  if (action === 'none') return null;
  if (action === 'blocked') {
    // no button: the bill of this table is printed and not paid, the server would refuse; say why
    return (
      <p className={cn('text-xs font-medium text-gray-500', className)} onClick={(event) => event.stopPropagation()}>
        {t('self_order.bill_printed')}
      </p>
    );
  }

  const open = state.tables.get(table);
  const working = busy === table;

  return (
    // the card around it is a tap target; the toggle must not start an order
    <div className={cn('flex items-center gap-2', className)} onClick={(event) => event.stopPropagation()}>
      {open && (
        <span className="flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-800">
          <QrCode className="h-3 w-3" />
          {t('self_order.open_badge', { minutes: minutesOpen(open.openedAt, now) })}
        </span>
      )}
      <button
        type="button"
        disabled={working || action === 'start-disabled'}
        title={action === 'start-disabled' ? t('self_order.store_closed') : undefined}
        onClick={() => onToggle(table, action === 'stop' ? 'stop' : 'start')}
        className={cn(
          'flex-1 rounded border px-2 py-1.5 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-50',
          action === 'stop'
            ? 'border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
            : 'border-emerald-400 bg-emerald-50 text-emerald-800 hover:bg-emerald-100'
        )}
      >
        {action === 'stop' ? t('self_order.stop') : t('self_order.start')}
      </button>
    </div>
  );
};

export default SelfOrderToggle;
