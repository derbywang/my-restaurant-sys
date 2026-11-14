import { useCallback, useEffect, useState } from 'react';
import { Spinner, Button } from '@ury/ui';
import { Clock } from 'lucide-react';
import { t } from '../i18n';
import { useRootStore, type RootState } from '../store/root-store';
import { getShiftState, RECHECK_MS, routeForOpening, type ShiftState } from '../lib/shift-gate';
import CaptainUserMenu from '../captain/components/CaptainUserMenu';

/**
 * The waiter has no shift of her own: she works on the one the cashier opened. Register open -> the screens; not open ->
 * a waiting page that asks again every 30 seconds (and by the button), so the screens come up by themselves.
 */
const WaiterShiftGate = ({ children }: { children: React.ReactNode }) => {
  const permissions = useRootStore((state: RootState) => state.permissions);
  const [shift, setShift] = useState<ShiftState | null>(null);
  const [checking, setChecking] = useState(false);

  const check = useCallback(async () => {
    setChecking(true);
    try {
      setShift(await getShiftState());
    } catch (error) {
      console.error('Failed to ask whether the register is open', error);
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    void check();
  }, [check]);

  const route = routeForOpening(permissions, shift);

  // keep asking while the register is closed
  useEffect(() => {
    if (route !== 'closed') return;
    const timer = setInterval(() => void check(), RECHECK_MS);
    return () => clearInterval(timer);
  }, [route, check]);

  if (route === 'open') return <>{children}</>;

  if (route === 'closed' || (route === 'loading' && !checking && shift === null && permissions)) {
    return (
      <div className="flex min-h-screen flex-col bg-gray-50">
        <div className="flex justify-end p-3">
          <CaptainUserMenu />
        </div>
        <div className="flex flex-1 items-center justify-center px-6">
          <div className="max-w-sm text-center">
            <Clock className="mx-auto mb-4 h-10 w-10 text-amber-600" />
            <h1 className="mb-2 text-xl font-semibold text-gray-900">{t('captain.shift_closed_title')}</h1>
            <p className="mb-6 text-sm text-gray-600">{t('captain.shift_closed_message')}</p>
            <Button onClick={() => void check()} disabled={checking}>
              {t('captain.shift_closed_recheck')}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Spinner message={t('common.checking_pos_status')} />
    </div>
  );
};

export default WaiterShiftGate;
