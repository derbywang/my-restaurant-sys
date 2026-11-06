import { useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { Spinner } from '@ury/ui';
import { useRootStore, type RootState } from '../store/root-store';
import { isWaiterOnly } from '../lib/pos-permissions';

/** How long the page waits for the permissions before it shows the register. */
const WAIT_MS = 4000;

/**
 * Where the POS opens: the waiter screen for someone who only takes orders, the dashboard for everyone else.
 * The permissions come from the server; if they do not arrive the register is shown (it shows nothing a user may not do).
 */
const HomeRedirect = () => {
  const permissions = useRootStore((state: RootState) => state.permissions);
  const [gaveUp, setGaveUp] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setGaveUp(true), WAIT_MS);
    return () => clearTimeout(timer);
  }, []);

  if (permissions) return <Navigate to={isWaiterOnly(permissions) ? '/order' : '/dashboard'} replace />;
  if (gaveUp) return <Navigate to="/dashboard" replace />;
  return <Spinner />;
};

export default HomeRedirect;
