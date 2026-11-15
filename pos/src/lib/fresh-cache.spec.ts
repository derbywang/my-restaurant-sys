import { describe, expect, it, vi } from 'vitest';
import { fetchFresh } from './fresh-cache';

function fakeStorage(initial: Record<string, string> = {}) {
  const data = { ...initial };
  return {
    data,
    getItem: (k: string) => (k in data ? data[k] : null),
    setItem: (k: string, v: string) => {
      data[k] = v;
    },
  } as unknown as Storage & { data: Record<string, string> };
}

// The list of the courses was kept in sessionStorage and used whenever it was there, so a register tab opened before the menu
// changed never saw a new course (2026-11-15: 「試験・握り」 imported, not in the tab's list). The server's answer wins; the
// copy is only for when the server cannot be reached.
describe('a list that is kept for the time the server cannot be reached', () => {
  it('shows what the server says, even when an older copy is kept', async () => {
    const storage = fakeStorage({ cats: JSON.stringify([{ name: 'Old' }]) });
    const result = await fetchFresh('cats', async () => [{ name: 'Old' }, { name: '試験・握り' }], storage);
    expect(result).toEqual([{ name: 'Old' }, { name: '試験・握り' }]);
  });

  it('keeps the answer for the next time', async () => {
    const storage = fakeStorage();
    await fetchFresh('cats', async () => [{ name: 'A' }], storage);
    expect(JSON.parse(storage.data.cats)).toEqual([{ name: 'A' }]);
  });

  it('uses the copy when the server cannot be reached', async () => {
    const storage = fakeStorage({ cats: JSON.stringify([{ name: 'Kept' }]) });
    const result = await fetchFresh('cats', async () => Promise.reject(new Error('offline')), storage);
    expect(result).toEqual([{ name: 'Kept' }]);
  });

  it('is an error when the server cannot be reached and nothing is kept', async () => {
    await expect(fetchFresh('cats', async () => Promise.reject(new Error('offline')), fakeStorage())).rejects.toThrow('offline');
  });

  it('a broken copy is not used', async () => {
    const storage = fakeStorage({ cats: '{not json' });
    await expect(fetchFresh('cats', async () => Promise.reject(new Error('offline')), storage)).rejects.toThrow('offline');
  });

  it('works without a storage (private mode that refuses it)', async () => {
    const refusing = {
      getItem: () => {
        throw new Error('denied');
      },
      setItem: () => {
        throw new Error('denied');
      },
    } as unknown as Storage;
    expect(await fetchFresh('cats', vi.fn(async () => [1]), refusing)).toEqual([1]);
  });
});
