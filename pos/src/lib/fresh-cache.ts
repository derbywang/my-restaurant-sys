/**
 * Ask the server; keep the answer in the tab's storage only for the time the server cannot be reached. The answer of the
 * server always wins: a list that was kept and used whenever it was there never showed what had changed on the server
 * (a course added after the tab was opened was not in the register's list).
 */
export async function fetchFresh<T>(key: string, fetcher: () => Promise<T>, storage: Storage = sessionStorage): Promise<T> {
  try {
    const fresh = await fetcher();
    try {
      storage.setItem(key, JSON.stringify(fresh));
    } catch {
      // storage refused (private mode, full): the list is still right
    }
    return fresh;
  } catch (error) {
    let kept: T | null = null;
    try {
      const text = storage.getItem(key);
      kept = text ? (JSON.parse(text) as T) : null;
    } catch {
      kept = null;
    }
    if (kept === null) throw error;
    return kept;
  }
}
