import { useEffect, useState, type ReactNode } from 'react';
import { useRootStore, type RootState } from '../store/root-store';
import { DashboardGuardView } from './DashboardGuardView';

/** How long the page waits for the permissions before it says they could not be loaded. */
const WAIT_MS = 4000;

/**
 * The dashboard shows the day's sales: someone who may not see them (a waiter) is sent to the waiter screen.
 * The server decides (`view_dashboard`); this only saves her an error screen, it is not the protection.
 * If the permissions never arrive (slow network) the page is NOT shown: she gets a "reload" notice instead.
 */
const DashboardGuard = ({ children }: { children: ReactNode }) => {
  const permissions = useRootStore((state: RootState) => state.permissions);
  const [gaveUp, setGaveUp] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setGaveUp(true), WAIT_MS);
    return () => clearTimeout(timer);
  }, []);

  return (
    <DashboardGuardView permissions={permissions} gaveUp={gaveUp}>
      {children}
    </DashboardGuardView>
  );
};

export default DashboardGuard;
