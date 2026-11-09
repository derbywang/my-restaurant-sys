import { useNavigate } from 'react-router-dom';
import { Bell, Volume2, VolumeX } from 'lucide-react';
import { cn } from '@ury/ui';
import { t } from '../i18n';
import { DINE_IN } from '../data/order-types';
import { bannerRequests, waitedSeconds, LATE_AFTER_SECONDS, type ServiceRequest } from '../lib/service-requests';
import { useServiceRequestStore } from '../store/service-request-store';
import { usePOSStore } from '../store/pos-store';

/**
 * The bar at the top of the POS while a 「お会計」 call is Open. It goes away when a member of staff opens the order of the
 * table (the call is then Acknowledged: quiet; the table card keeps showing it until the bill is printed, paid or cancelled).
 * Touching an entry opens that table's order.
 */
const ServiceRequestBanner: React.FC<{ onOpen?: (request: ServiceRequest) => void }> = ({ onOpen }) => {
  const navigate = useNavigate();
  const requests = useServiceRequestStore((state) => state.requests);
  const now = useServiceRequestStore((state) => state.now);
  const muted = useServiceRequestStore((state) => state.muted);
  const toggleMuted = useServiceRequestStore((state) => state.toggleMuted);
  const setSelectedOrderType = usePOSStore((state) => state.setSelectedOrderType);
  const setSelectedTable = usePOSStore((state) => state.setSelectedTable);

  const open = bannerRequests(requests, now);
  if (open.length === 0) return null;

  return (
    <div role="alert" className="flex items-center gap-3 bg-amber-100 px-4 py-2 text-sm text-amber-950 shadow-sm">
      <Bell className="h-4 w-4 shrink-0 animate-pulse text-amber-700" />
      <span className="shrink-0 font-semibold">{t('service_request.banner_title')}</span>
      <div className="flex flex-1 flex-wrap gap-2">
        {open.map((request) => {
          const seconds = waitedSeconds(request, now);
          return (
            <button
              key={request.name}
              type="button"
              onClick={() => {
                if (onOpen) {
                  onOpen(request);
                  return;
                }
                // the register: the order of the table in the POS
                setSelectedOrderType(DINE_IN);
                setSelectedTable(request.table, request.room || null);
                navigate('/pos');
              }}
              className={cn(
                'rounded border px-2 py-1 font-medium transition hover:bg-white',
                seconds > LATE_AFTER_SECONDS ? 'border-red-400 bg-red-50 text-red-800' : 'border-amber-400 bg-amber-50'
              )}
            >
              {t('service_request.banner_item', { table: request.table, minutes: Math.floor(seconds / 60) })}
            </button>
          );
        })}
      </div>
      <button
        type="button"
        onClick={toggleMuted}
        title={muted ? t('service_request.unmute') : t('service_request.mute')}
        aria-label={muted ? t('service_request.unmute') : t('service_request.mute')}
        className="shrink-0 rounded p-1 hover:bg-amber-200"
      >
        {muted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
      </button>
    </div>
  );
};

export default ServiceRequestBanner;
