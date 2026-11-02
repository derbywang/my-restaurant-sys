// The default customer: the `customer` of the POS Profile (「一般のお客様」 on a Japanese site),
// chosen for a new order so the cashier does not search a customer for every bill.
// It is filled in at explicit moments only (a new order, the next order, an order type change),
// never "whenever the customer is empty": the cashier can clear it and it stays cleared.
import type { Customer } from '../store/pos-store';
import type { OrderType } from '../data/order-types';

export interface CustomerRecord {
  name: string;
  customer_name?: string | null;
  mobile_number?: string | null;
  disabled?: number | null;
}

// Delivery and phone orders need the guest's name and phone: the cashier picks the customer.
const NAMED_CUSTOMER_ORDER_TYPES: OrderType[] = ['Delivery', 'Phone In'];

export function toDefaultCustomer(record: CustomerRecord | null | undefined): Customer | null {
  if (!record || record.disabled) return null;
  return {
    id: record.name,
    name: record.customer_name || record.name,
    phone: record.mobile_number || '',
  };
}

/** The default customer to compare with: the loaded one, else the one the POS Profile names (its
 * record may not have loaded), so a default customer on screen is still recognised as such. */
export function defaultCustomerOf(
  loaded: Customer | null,
  profileCustomer: string | null | undefined
): Customer | null {
  if (loaded) return loaded;
  return profileCustomer ? { id: profileCustomer, name: profileCustomer, phone: '' } : null;
}

/** The customer a new order of `orderType` starts with. */
export function freshOrderCustomer(defaultCustomer: Customer | null, orderType: OrderType): Customer | null {
  return customerAfterOrderTypeChange(null, defaultCustomer, orderType);
}

/** The customer after the order type changed: a customer the cashier chose is kept; the default
 * customer is dropped for delivery / phone orders and filled in again for dine in / take away. */
export function customerAfterOrderTypeChange(
  current: Customer | null,
  defaultCustomer: Customer | null,
  newType: OrderType
): Customer | null {
  if (newType === 'Aggregators') return current;
  if (NAMED_CUSTOMER_ORDER_TYPES.includes(newType)) {
    return current && defaultCustomer && current.id === defaultCustomer.id ? null : current;
  }
  return current ?? defaultCustomer;
}

/** An empty tab nothing was done in yet: the only place the default customer arriving late
 * (the profile loads after the page) may be filled in. */
export function isFreshOrder(state: {
  activeOrders: unknown[];
  selectedCustomer: Customer | null;
  isUpdatingOrder: boolean;
  orderLoading: boolean;
}): boolean {
  return (
    state.activeOrders.length === 0 &&
    !state.selectedCustomer &&
    !state.isUpdatingOrder &&
    !state.orderLoading
  );
}

/** What the backend takes as `customer`: the docname (`id`), not the customer name, which two
 * customers can share. */
export function customerId(customer: Customer | null | undefined): string | undefined {
  return customer?.id || undefined;
}
