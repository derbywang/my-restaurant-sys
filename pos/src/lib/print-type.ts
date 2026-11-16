// How the register prints (`print_type`: "server", "qz", "network", "socket") is a setting of the shop. The POS keeps the
// profile it fetched at login in sessionStorage, so a shop that chose a printer afterwards would not be heard by a screen
// that is already logged in. This asks the server again each time the POS opens, for this one field only (the rest of the
// cached profile is left alone), and keeps the cached way when the server cannot be asked.

interface WithPrintType {
  print_type?: string | null;
}

export async function refreshPrintType<T extends WithPrintType>(
  cached: T | null,
  fetchLimited: () => Promise<WithPrintType | null | undefined>
): Promise<{ profile: T | null; changed: boolean }> {
  if (!cached) return { profile: cached, changed: false };
  try {
    const fresh = await fetchLimited();
    const printType = fresh?.print_type;
    if (typeof printType !== 'string' || printType === cached.print_type) return { profile: cached, changed: false };
    return { profile: { ...cached, print_type: printType }, changed: true };
  } catch {
    return { profile: cached, changed: false };
  }
}
