import { useEffect, useState } from 'react';
import { createConnectionMonitor, startConnectionMonitor } from '@ury/core';
import { t } from '../i18n';

/** Is the server answering? A small request that needs no login. Five seconds is the longest a look may take. */
async function serverAnswers(): Promise<boolean> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 5000);
  try {
    const response = await fetch('/api/method/ping', { cache: 'no-store', signal: controller.signal });
    return response.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * The red bar over every screen of the POS while the server cannot be reached (Wi-Fi gone, the laptop restarting): the
 * register and the waiter's screen would otherwise look alive while orders and payments silently fail. It goes away by
 * itself when the server answers again.
 */
const ConnectionBanner: React.FC = () => {
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    const monitor = createConnectionMonitor({ check: serverAnswers, onChange: (online) => setOffline(!online) });
    return startConnectionMonitor(monitor, window);
  }, []);

  if (!offline) return null;
  return (
    <div
      role="alert"
      data-testid="connection-banner"
      className="fixed inset-x-0 top-0 z-[100] bg-red-600 px-4 py-3 text-center text-sm font-semibold text-white shadow-lg"
    >
      {t('connection.lost')}
    </div>
  );
};

export default ConnectionBanner;
