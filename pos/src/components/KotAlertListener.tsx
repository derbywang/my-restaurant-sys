import { useCallback, useEffect, useRef, useState } from 'react';
import { useKotErrorChannels } from '../lib/realtime';
import { showToast } from '@ury/ui';
import { usePOSStore } from '../store/pos-store';
import { getProductionUnitsForBranch, getRecentKotAlerts } from '../lib/production-api';
import { KOT_ALERT_POLL_MS, createAlertTracker, pollKotAlerts } from '../lib/kot-alert-poll';
import { kotAlertMessage, createAlertDedupe } from '../lib/kot-alert';
import { t } from '../i18n';

/**
 * KotAlertListener: A headless component that subscribes to all KOT error channels
 * for the current branch and displays toast notifications when errors occur.
 *
 * On mount, this component:
 * 1. Fetches the list of production units for the current branch
 * 2. Subscribes to the kot_error_<branch>_<production> channel for each production unit
 * 3. Shows a toast error when the backend broadcasts a KOT validation error
 *
 * Multiple production units are supported: a single POS terminal can serve multiple
 * production stations, so all channels are monitored simultaneously.
 */
const KotAlertListener: React.FC = () => {
  const { posProfile } = usePOSStore();
  const branch = posProfile?.branch || '';

  const [productionUnits, setProductionUnits] = useState<string[]>([]);

  // Fetch production units on mount and when branch changes
  useEffect(() => {
    if (!branch) {
      setProductionUnits([]);
      return;
    }

    let isMounted = true;

    const loadProductionUnits = async () => {
      try {
        const units = await getProductionUnitsForBranch();
        if (isMounted) {
          setProductionUnits(units);
          if (units.length === 0) {
            console.warn(
              'KotAlertListener: no production units found for branch. ' +
              'KOT error monitoring will not be active.'
            );
          }
        }
      } catch (error) {
        console.error('KotAlertListener: failed to load production units:', error);
        if (isMounted) {
          setProductionUnits([]);
        }
      }
    };

    loadProductionUnits();

    return () => {
      isMounted = false;
    };
  }, [branch]);

  // The same alert comes once per production unit's channel, and again by asking the server: show it once
  const seen = useRef(createAlertDedupe(3000));
  const tracker = useRef(createAlertTracker());
  const showAlert = useCallback((payload: Record<string, unknown>) => {
    if (!tracker.current.isNew(payload)) return;
    if (!seen.current(payload)) return;
    showToast.error(kotAlertMessage(payload, (key, params) => t(key, params)));
  }, []);
  const handleKotError = useCallback((payload: Record<string, unknown>) => showAlert(payload), [showAlert]);

  // The second way: an iPad that slept never heard the socket, so ask the server now and then (and on waking up)
  useEffect(() => {
    if (!branch) return;
    const look = () =>
      pollKotAlerts(
        tracker.current,
        getRecentKotAlerts,
        (payload) => {
          if (seen.current(payload)) showToast.error(kotAlertMessage(payload, (key, params) => t(key, params)));
        }
      );
    look();
    const timer = setInterval(look, KOT_ALERT_POLL_MS);
    const onVisible = () => {
      if (document.visibilityState === 'visible') look();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [branch]);

  // Subscribe to all production unit channels
  useKotErrorChannels(branch, productionUnits, handleKotError);

  // This component has no visible UI
  return null;
};

export default KotAlertListener;
