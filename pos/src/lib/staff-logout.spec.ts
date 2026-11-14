import { describe, expect, it, vi } from 'vitest';

import { hasUnsentChanges, LOGIN_URL, logoutToLogin } from './staff-logout';

describe('what the waiter would lose by logging out', () => {
  it('has nothing to lose when every dish was sent', () => {
    expect(hasUnsentChanges({ newOrChanged: [], reductionPending: [] })).toBe(false);
  });

  it('loses the dishes that were added and not sent', () => {
    expect(hasUnsentChanges({ newOrChanged: [{}], reductionPending: [] })).toBe(true);
  });

  it('loses the dishes that were taken back and not sent', () => {
    expect(hasUnsentChanges({ newOrChanged: [], reductionPending: [{}] })).toBe(true);
  });
});

describe('logging out', () => {
  it('ends the login and then goes to the login page', async () => {
    const calls: string[] = [];
    const logout = vi.fn(async () => {
      calls.push('logout');
    });
    const go = vi.fn((url: string) => {
      calls.push(`go ${url}`);
    });
    const onError = vi.fn();

    expect(await logoutToLogin({ logout, go, onError })).toBe(true);
    expect(calls).toEqual(['logout', `go ${LOGIN_URL}`]);
    expect(onError).not.toHaveBeenCalled();
  });

  it('comes back to the POS after the next login', () => {
    expect(LOGIN_URL).toBe('/login?redirect-to=%2Fpos');
  });

  it('stays where it is and says so when the logout fails', async () => {
    const go = vi.fn();
    const onError = vi.fn();
    const logout = vi.fn(async () => {
      throw new Error('offline');
    });

    expect(await logoutToLogin({ logout, go, onError })).toBe(false);
    expect(go).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledTimes(1);
  });
});
