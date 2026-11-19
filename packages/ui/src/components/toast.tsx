import { toast, ToastContainer } from 'react-toastify';
import { CheckCircle, XCircle, Info, AlertTriangle } from 'lucide-react';
import 'react-toastify/dist/ReactToastify.css';

// Custom CSS for toast styling
import './toast.css';

const toastIcons = {
  success: <CheckCircle className="w-5 h-5" />,
  error: <XCircle className="w-5 h-5" />,
  info: <Info className="w-5 h-5" />,
  warning: <AlertTriangle className="w-5 h-5" />,
};

export const showToast = {
  success: (message: string) => {
    toast.success(message, {
      position: 'top-right',
      autoClose: 2000,
      hideProgressBar: false,
      closeOnClick: true,
      pauseOnHover: true,
      draggable: true,
      progress: undefined,
      theme: 'colored',
      icon: toastIcons.success,
      className: 'toast-success',
    });
  },
  error: (message: string) => {
    toast.error(message, {
      position: 'top-right',
      autoClose: 2000,
      hideProgressBar: false,
      closeOnClick: true,
      pauseOnHover: true,
      draggable: true,
      progress: undefined,
      theme: 'colored',
      icon: toastIcons.error,
      className: 'toast-error',
    });
  },
  /**
   * A red message that stays until someone touches it (or the same `id` is shown again): for what the staff must not miss and
   * cannot be allowed to lose behind the next screen (the drawer did not open after a payment). Solid red, large, bold.
   */
  errorStay: (message: string, id?: string) => {
    toast.error(message, {
      position: 'top-right',
      autoClose: false,
      hideProgressBar: true,
      closeOnClick: true,
      pauseOnHover: false,
      draggable: false,
      theme: 'colored',
      icon: toastIcons.error,
      className: 'toast-error-sticky',
      toastId: id,
    });
  },
  /**
   * A message with one button, for a few seconds (the receipt that can be printed after a payment): it goes away by itself, and a
   * touch beside the button does not close it, so that the cashier can reach the button with a wet hand.
   */
  withAction: (message: string, actionLabel: string, onAction: () => void, id?: string) => {
    toast.success(
      ({ closeToast }) => (
        <div className="flex items-center justify-between gap-3">
          <span className="flex-1 text-sm font-semibold">{message}</span>
          <button
            type="button"
            className="shrink-0 rounded bg-white px-3 py-1.5 text-sm font-bold text-gray-900"
            onClick={() => {
              closeToast?.();
              onAction();
            }}
          >
            {actionLabel}
          </button>
        </div>
      ),
      {
        position: 'top-right',
        autoClose: 10000,
        hideProgressBar: false,
        closeOnClick: false,
        pauseOnHover: true,
        draggable: false,
        theme: 'colored',
        icon: toastIcons.success,
        className: 'toast-success',
        toastId: id,
      }
    );
  },
  warning: (message: string) => {
    toast.warning(message, {
      position: 'top-right',
      autoClose: 2000,
      hideProgressBar: false,
      closeOnClick: true,
      pauseOnHover: true,
      draggable: true,
      progress: undefined,
      theme: 'colored',
      icon: toastIcons.warning,
      className: 'toast-warning',
    });
  },
  info: (message: string) => {
    toast.info(message, {
      position: 'top-right',
      autoClose: 2000,
      hideProgressBar: false,
      closeOnClick: true,
      pauseOnHover: true,
      draggable: true,
      progress: undefined,
      theme: 'colored',
      icon: toastIcons.info,
      className: 'toast-info',
    });
  },
};

export const ToastProvider = () => {
  return (
    <ToastContainer
      position="top-right"
      autoClose={2000}
      hideProgressBar={false}
      newestOnTop
      closeOnClick
      rtl={false}
      pauseOnFocusLoss
      draggable
      pauseOnHover
      theme="colored"
    />
  );
};
