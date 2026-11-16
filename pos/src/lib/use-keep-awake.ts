import { useEffect } from 'react';
import { createWakeLock } from '@ury/core';

/** Keep the screen awake while the page is open (the register's iPad must not go dark in the middle of service). */
export function useKeepAwake(): void {
  useEffect(() => {
    const lock = createWakeLock(navigator as never, document as never);
    void lock.start();
    return () => void lock.stop();
  }, []);
}
