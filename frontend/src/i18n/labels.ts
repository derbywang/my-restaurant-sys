import { tOr } from './index';

// Backend data values (order type, invoice status) mapped to locale keys.
// A value with no translation is shown as-is.
const ORDER_TYPE_KEYS: Record<string, string> = {
  'Dine In': 'dine_in',
  'Take Away': 'take_away',
  Takeaway: 'take_away',
  Delivery: 'delivery',
  'Phone In': 'phone_in',
  Aggregators: 'aggregators',
};

const ORDER_STATUS_KEYS: Record<string, string> = {
  Draft: 'draft',
  Unbilled: 'unbilled',
  'Recently Paid': 'recently_paid',
  Paid: 'paid',
  Consolidated: 'consolidated',
  Return: 'return',
};

export const orderTypeLabel = (value: string): string =>
  ORDER_TYPE_KEYS[value] ? tOr(`order_types.${ORDER_TYPE_KEYS[value]}`, value) : value;

export const orderStatusLabel = (value: string): string =>
  ORDER_STATUS_KEYS[value] ? tOr(`order_status_types.${ORDER_STATUS_KEYS[value]}`, value) : value;
