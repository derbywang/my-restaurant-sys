import { useEffect, useState } from 'react';
import { previewCartTotals, type OrderTotals } from '../lib/order-totals-api';

interface CartLine {
  id: string;
  name: string;
  quantity: number;
}

interface CartTotalsInput {
  lines: CartLine[];
  posProfile?: string;
  orderType: string;
  customer?: string;
  table?: string | null;
  invoice?: string | null;
}

export type CartTotalsState =
  | { status: 'empty' }
  | { status: 'loading'; totals: OrderTotals | null }
  | { status: 'ready'; totals: OrderTotals }
  | { status: 'error'; totals: null };

const DEBOUNCE_MS = 250;

/**
 * The tax-inclusive amounts of the cart as the server calculates them. The browser never
 * calculates tax or rounding itself (the tax of each rate is rounded down on the server),
 * so every change of the cart asks again; an answer that arrives after a newer request
 * was made is dropped. While asking, the previous amounts stay on screen.
 */
export function useCartTotals(input: CartTotalsInput): CartTotalsState {
  const { lines, posProfile, orderType, customer, table, invoice } = input;
  const [state, setState] = useState<CartTotalsState>({ status: 'empty' });

  const key = JSON.stringify([
    lines.map((line) => [line.id, line.quantity]),
    posProfile,
    orderType,
    customer,
    table,
    invoice,
  ]);

  useEffect(() => {
    if (lines.length === 0 || !posProfile) {
      setState({ status: 'empty' });
      return;
    }

    let current = true;
    setState((previous) => ({
      status: 'loading',
      totals: previous.status === 'empty' || previous.status === 'error' ? null : previous.totals,
    }));

    const timer = setTimeout(() => {
      previewCartTotals({
        items: lines.map((line) => ({ item: line.id, item_name: line.name, qty: line.quantity })),
        pos_profile: posProfile,
        order_type: orderType,
        customer,
        table: table || undefined,
        invoice,
      })
        .then((totals) => current && setState({ status: 'ready', totals }))
        .catch((error) => {
          console.error('Failed to preview the cart totals:', error);
          if (current) setState({ status: 'error', totals: null });
        });
    }, DEBOUNCE_MS);

    return () => {
      current = false;
      clearTimeout(timer);
    };
    // `key` stands for every input above
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return state;
}
