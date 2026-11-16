import { useCallback } from 'react';
import { showToast } from '@ury/ui';
import { t } from '../i18n';
import { answerStaffCalls, callNames } from './service-requests';
import { useServiceRequestStore } from '../store/service-request-store';

/** 「対応済み」 for the calls for the staff at a table: resolve them, read the calls again, say so when it failed. */
export function useAnswerCalls() {
  const requests = useServiceRequestStore((state) => state.requests);
  const refresh = useServiceRequestStore((state) => state.refresh);
  return useCallback(
    async (table: string) => {
      const failure = await answerStaffCalls(callNames(requests, table, 'Assistance'), undefined, refresh);
      if (failure) showToast.error(t('service_request.answer_failed'));
    },
    [requests, refresh]
  );
}
