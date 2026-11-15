import { fetchFresh } from './fresh-cache';
import { getRooms, getTableCount, type Room } from './table-api';

/** The rooms of the branch: the server's list; the copy kept in the tab only when the server cannot be reached. */
export function loadRooms(branch: string): Promise<Room[]> {
  return fetchFresh(`ury_rooms_${branch}`, () => getRooms(branch));
}

/** How many tables each room has (by the room's name), asked again each time. */
export function loadRoomCounts(branch: string, rooms: Room[]): Promise<Record<string, number>> {
  return fetchFresh(`ury_room_counts_${branch}`, async () => {
    const counts = await Promise.all(rooms.map((room) => getTableCount(room.name, room.branch)));
    return rooms.reduce(
      (acc, room, index) => {
        acc[room.name] = counts[index];
        return acc;
      },
      {} as Record<string, number>
    );
  });
}
