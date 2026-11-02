export { createFrappeClient, call, db, auth } from './frappe/client';
export { getLoggedUser, getUserRoles, logout } from './frappe/auth';
export { isUserRestrictedFromTableOrders, canCaptainTransfer, derivePOSCapabilities } from './frappe/roles';
export type { POSCapabilities } from './frappe/roles';
export { parseFrappeError } from './frappe/errors';
export type { User, PosProfileCombined } from './types';
export { storage } from './storage';
export { getCurrency, setCurrency } from './currency';
export { formatCurrency, formatCompactCurrency, formatInvoiceTime, flt } from './format';
export { initPrinting, loadQzPrinter, disconnectQzPrinter, printWithQz } from './print/qz';
export {
  buildSocketUrl,
  keepTryingToConnect,
  SOCKET_RECONNECT_OPTIONS,
  SLOW_RETRY_MS,
} from './realtime';
export type { SocketUrlInput, ReconnectableSocket } from './realtime';
export { validateFieldValue } from './utils/validateField';
export type { ValidationMessages } from './utils/validateField';
export { setStaffLanguage } from './frappe/language';
export {
  initI18n,
  t,
  tOr,
  getActiveLanguage,
  getActiveDirection,
  applyDocumentLocale,
  resolveLanguage,
  DEFAULT_LANGUAGE,
  SUPPORTED_LANGUAGES,
  MENU_LANGUAGES,
} from './i18n';
export type { LocaleLoaders } from './i18n';
