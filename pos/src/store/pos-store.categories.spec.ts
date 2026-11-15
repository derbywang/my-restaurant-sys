import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../lib/menu-api', () => ({ getRestaurantMenu: vi.fn(async () => []), getAggregatorMenu: vi.fn(async () => []) }));
vi.mock('../lib/customer-api', () => ({
  getCustomerGroups: vi.fn(async () => []),
  getCustomerTerritories: vi.fn(async () => []),
  getCustomerRecord: vi.fn(async () => null),
}));
const courses = vi.fn();
vi.mock('../lib/menu-course-api', () => ({ getMenuCourses: () => courses() }));

import { usePOSStore } from './pos-store';

describe('the course tabs of the register', () => {
  beforeEach(() => {
    const data: Record<string, string> = { menuCategories: JSON.stringify([{ name: 'Starters', label: 'Starters' }]) };
    vi.stubGlobal('sessionStorage', {
      getItem: (k: string) => data[k] ?? null,
      setItem: (k: string, v: string) => {
        data[k] = v;
      },
      removeItem: (k: string) => {
        delete data[k];
      },
    });
    usePOSStore.setState({ categories: [] });
  });

  it('a course added after the tab kept its list is in the list (the copy in the tab is not trusted)', async () => {
    courses.mockResolvedValue([
      { name: 'Starters', label: 'Starters' },
      { name: '試験・握り', label: '試験・握り' },
    ]);
    await usePOSStore.getState().fetchCategories();
    expect(usePOSStore.getState().categories.map((c) => c.name)).toEqual(['Starters', '試験・握り']);
  });

  it('the kept list is used when the server cannot be reached', async () => {
    courses.mockRejectedValue(new Error('offline'));
    await usePOSStore.getState().fetchCategories();
    expect(usePOSStore.getState().categories.map((c) => c.name)).toEqual(['Starters']);
  });
});
