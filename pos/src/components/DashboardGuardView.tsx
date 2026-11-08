import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { Spinner } from '@ury/ui';
import { canViewDashboard, type PosPermissions } from '../lib/pos-permissions';
import { t } from '../i18n';

interface Props {
  permissions: PosPermissions | null | undefined;
  /** The permissions did not arrive in time. */
  gaveUp: boolean;
  children: ReactNode;
}

/**
 * What the dashboard guard shows. The page (`children`) is only rendered once the server has said this user may
 * see the sales; while the permissions are missing it shows a spinner, and after the wait a "reload" notice, never
 * the page (its sales requests would only fail one by one).
 */
export const DashboardGuardView = ({ permissions, gaveUp, children }: Props) => {
  if (permissions) return canViewDashboard(permissions) ? <>{children}</> : <Navigate to="/order" replace />;
  if (gaveUp) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-6 text-center" role="alert">
        <p>{t('pos.permissions_unavailable')}</p>
        <button type="button" className="rounded border px-4 py-2" onClick={() => window.location.reload()}>
          {t('pos.reload_page')}
        </button>
      </div>
    );
  }
  return <Spinner />;
};
