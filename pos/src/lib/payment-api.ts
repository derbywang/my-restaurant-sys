import { call } from '@ury/core';
import { fetchFresh } from './fresh-cache';

interface PaymentMode {
  mode_of_payment: string;
  opening_amount: number;
  /** Mode of Payment type: "Cash", "Bank", ... Missing in a response cached by an old session. */
  type?: string;
}

interface PaymentModeResponse {
  message: PaymentMode[];
}

let inFlight: Promise<PaymentMode[]> | null = null;

/** The modes the server has now (the copy kept in the tab only when it cannot be reached); asked for together, one request. */
function loadPaymentModes(): Promise<PaymentMode[]> {
  if (!inFlight) {
    inFlight = (async () => {
      try {
        return await fetchFresh('payment_mode_list', async () => {
          const response = await call.get<PaymentModeResponse>("ury.ury_pos.api.getModeOfPayment");
          return response.message;
        });
      } finally {
        inFlight = null;
      }
    })();
  }
  return inFlight;
}

export const getPaymentModes = async (): Promise<string[]> =>
  (await loadPaymentModes()).map((mode) => mode.mode_of_payment);

/** Mode of Payment -> type ("Cash" is the only one that gives change). */
export const getPaymentModeTypes = async (): Promise<Record<string, string>> => {
  const types: Record<string, string> = {};
  for (const mode of await loadPaymentModes()) {
    if (mode.type) types[mode.mode_of_payment] = mode.type;
  }
  return types;
};
