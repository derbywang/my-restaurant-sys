import { HandHelping } from 'lucide-react';
import { cn } from '@ury/ui';
import { t } from '../i18n';
import type { CardState } from '../lib/service-requests';

/**
 * The line of a table card for 「呼び出し」 (the guest called a member of staff): the minutes waited, red after three, and
 * the button 「対応済み」 that a member of staff presses after going to the table. A bill call has its own line.
 */
const StaffCallRow: React.FC<{ state: CardState | null; onAnswer?: () => void; className?: string }> = ({ state, onAnswer, className }) => {
  if (!state) return null;
  return (
    <div
      data-testid="staff-call"
      className={cn(
        'flex items-center gap-2 rounded-md px-2 py-1 text-sm font-semibold',
        state.late ? 'bg-red-100 text-red-800' : 'bg-sky-100 text-sky-900',
        className
      )}
    >
      <HandHelping className={cn('h-4 w-4 shrink-0', !state.quiet && 'animate-bounce')} />
      <span>{t('service_request.call_staff')}</span>
      <span className="font-medium">{t('service_request.minutes', { minutes: state.minutes })}</span>
      {onAnswer && (
        <button
          type="button"
          data-testid="staff-call-done"
          onClick={(event) => {
            event.stopPropagation();
            onAnswer();
          }}
          className="ml-auto rounded border border-current bg-white/80 px-2 py-0.5 text-xs font-semibold"
        >
          {t('service_request.done')}
        </button>
      )}
    </div>
  );
};

export default StaffCallRow;
