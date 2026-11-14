// Logging out of the POS: shared by the cashier's header and the waiter's screens (several waiters share a tablet).

/** After the next login the user comes back to the POS. */
export const LOGIN_URL = '/login?redirect-to=%2Fpos';

/** What the waiter has on the screen and has not sent to the kitchen yet: logging out throws it away. */
export function hasUnsentChanges(lines: { newOrChanged: unknown[]; reductionPending: unknown[] }): boolean {
  return lines.newOrChanged.length > 0 || lines.reductionPending.length > 0;
}

interface LogoutDeps {
  logout: () => Promise<unknown>;
  go: (url: string) => void;
  onError: () => void;
}

/** Ends the login, then goes to the login page. When the logout fails the user stays where they are. */
export async function logoutToLogin({ logout, go, onError }: LogoutDeps): Promise<boolean> {
  try {
    await logout();
  } catch {
    onError();
    return false;
  }
  go(LOGIN_URL);
  return true;
}
