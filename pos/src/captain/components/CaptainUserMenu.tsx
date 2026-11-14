import { useEffect, useRef, useState } from 'react';
import { ChevronDown, LogOut, User } from 'lucide-react';
import { Button, showToast } from '@ury/ui';
import { logout } from '@ury/core';
import { t } from '../../i18n';
import { useRootStore } from '../../store/root-store';
import type { RootState } from '../../store/root-store';
import { logoutToLogin } from '../../lib/staff-logout';

interface CaptainUserMenuProps {
  /** Dishes on the screen that were not sent yet: logging out throws them away, so the waiter is asked first. */
  hasUnsent?: boolean;
}

/** The waiter's account: the name, the account and the logout (several waiters share one tablet). */
const CaptainUserMenu = ({ hasUnsent = false }: CaptainUserMenuProps) => {
  const user = useRootStore((state: RootState) => state.user);
  const [open, setOpen] = useState(false);
  const [asking, setAsking] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);

  const leave = () =>
    logoutToLogin({
      logout,
      go: (url) => {
        window.location.href = url;
      },
      onError: () => showToast.error(t('errors.failed_logout')),
    });

  const onLogout = () => {
    setOpen(false);
    if (hasUnsent) setAsking(true);
    else void leave();
  };

  return (
    <div className="relative" ref={ref}>
      <Button variant="ghost" size="icon" aria-label={user?.full_name || t('captain.account')} onClick={() => setOpen(!open)}>
        <User className="h-5 w-5" />
        <ChevronDown className="h-3 w-3" />
      </Button>

      {open && (
        <div className="absolute end-0 z-50 mt-2 w-60 rounded-lg border border-gray-200 bg-white shadow-lg">
          <div className="border-b border-gray-200 p-4">
            <p className="text-sm font-medium text-gray-900">{user?.full_name || ''}</p>
            <p className="break-all text-sm text-gray-500">{user?.name || ''}</p>
          </div>
          <div className="py-2">
            <Button
              variant="ghost"
              className="flex w-full items-center justify-start px-4 py-2 text-sm text-red-600 hover:bg-red-50 hover:text-red-700"
              onClick={onLogout}
            >
              <LogOut className="me-3 h-4 w-4" />
              {t('header.logout')}
            </Button>
          </div>
        </div>
      )}

      {asking && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50">
          <div className="mx-4 w-full max-w-md rounded-lg bg-white p-6 shadow-xl" role="alertdialog">
            <h2 className="mb-2 text-lg font-semibold text-gray-900">{t('captain.logout_unsent_title')}</h2>
            <p className="mb-6 text-sm text-gray-600">{t('captain.logout_unsent_message')}</p>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setAsking(false)}>
                {t('captain.logout_keep_working')}
              </Button>
              <Button variant="destructive" onClick={() => void leave()}>
                {t('captain.logout_anyway')}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default CaptainUserMenu;
