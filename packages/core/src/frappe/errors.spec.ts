import { describe, expect, it } from 'vitest';
import { isPermissionError } from './errors';

describe('isPermissionError', () => {
  it('knows the exception type Frappe sends', () => {
    expect(isPermissionError({ exc_type: 'PermissionError', message: 'x' })).toBe(true);
    expect(isPermissionError({ response: { exc_type: 'PermissionError' } })).toBe(true);
  });

  it('knows it from the exception text and from HTTP 403', () => {
    expect(isPermissionError({ exception: 'frappe.exceptions.PermissionError: Only a cashier can do this.' })).toBe(true);
    expect(isPermissionError({ httpStatus: 403 })).toBe(true);
  });

  it('is not fooled by other errors', () => {
    expect(isPermissionError({ exc_type: 'ValidationError', message: 'Not permitted' })).toBe(false);
    expect(isPermissionError({ exception: 'frappe.exceptions.ValidationError: Error while settling order' })).toBe(false);
    expect(isPermissionError(new Error('Network down'))).toBe(false);
    expect(isPermissionError(null)).toBe(false);
    expect(isPermissionError('PermissionError')).toBe(false);
  });
});
