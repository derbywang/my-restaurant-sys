import { beforeEach, describe, expect, it, vi } from 'vitest';

const getRooms = vi.fn();
const getTableCount = vi.fn();
vi.mock('./table-api', () => ({ getRooms: (...a: unknown[]) => getRooms(...a), getTableCount: (...a: unknown[]) => getTableCount(...a) }));

import { loadRoomCounts, loadRooms } from './rooms';

function stubStorage(initial: Record<string, string>) {
  const data = { ...initial };
  vi.stubGlobal('sessionStorage', {
    getItem: (k: string) => data[k] ?? null,
    setItem: (k: string, v: string) => {
      data[k] = v;
    },
    removeItem: (k: string) => {
      delete data[k];
    },
  });
  return data;
}

// The rooms and the number of tables of each were kept in the tab and used whenever they were there: rooms imported or
// added after the register was opened did not show in the table choice until the tab was closed (2026-11-15).
describe('the rooms of the branch', () => {
  beforeEach(() => {
    getRooms.mockReset();
    getTableCount.mockReset();
  });

  it('shows the rooms the server has now, not the list kept in the tab', async () => {
    stubStorage({ 'ury_rooms_三友寿司': JSON.stringify([{ name: 'Main Dining', branch: '三友寿司' }]) });
    getRooms.mockResolvedValue([
      { name: 'Main Dining', branch: '三友寿司' },
      { name: 'テラス', branch: '三友寿司' },
    ]);
    expect((await loadRooms('三友寿司')).map((r) => r.name)).toEqual(['Main Dining', 'テラス']);
    expect(getRooms).toHaveBeenCalledWith('三友寿司');
  });

  it('uses the list kept in the tab only when the server cannot be reached', async () => {
    stubStorage({ 'ury_rooms_三友寿司': JSON.stringify([{ name: 'Main Dining', branch: '三友寿司' }]) });
    getRooms.mockRejectedValue(new Error('offline'));
    expect((await loadRooms('三友寿司')).map((r) => r.name)).toEqual(['Main Dining']);
  });

  it('the number of tables of each room is asked again too', async () => {
    stubStorage({ 'ury_room_counts_三友寿司': JSON.stringify({ 'Main Dining': 10 }) });
    getTableCount.mockImplementation(async (room: string) => (room === 'Main Dining' ? 12 : 4));
    const rooms = [
      { name: 'Main Dining', branch: '三友寿司' },
      { name: 'テラス', branch: '三友寿司' },
    ];
    expect(await loadRoomCounts('三友寿司', rooms)).toEqual({ 'Main Dining': 12, テラス: 4 });
  });
});
