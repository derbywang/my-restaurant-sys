import { call } from '@ury/core';

interface PaymentMode {
  mode_of_payment: string;
  opening_amount: number;
  /** Mode of Payment type: "Cash", "Bank", ... Missing in a response cached by an old session. */
  type?: string;
}

interface PaymentModeResponse {
  message: PaymentMode[];
}

async function loadPaymentModes(): Promise<PaymentMode[]> {
  const cached = sessionStorage.getItem('payment_mode_list');
  if (cached) {
    return JSON.parse(cached);
  }
  try {
    const response = await call.get<PaymentModeResponse>("ury.ury_pos.api.getModeOfPayment");
    sessionStorage.setItem('payment_mode_list', JSON.stringify(response.message));
    return response.message;
  } catch (error) {
    console.error('Failed to fetch payment modes:', error);
    throw error;
  }
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
