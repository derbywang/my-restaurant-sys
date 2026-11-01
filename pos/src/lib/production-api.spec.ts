import { describe, expect, it, vi } from 'vitest';

const get = vi.fn();
vi.mock('@ury/core', () => ({ call: { get: (...args: unknown[]) => get(...args) } }));

import { getProductionUnitsForBranch } from './production-api';

describe('getProductionUnitsForBranch', () => {
  it('reads the names from the message of the Frappe response', async () => {
    get.mockResolvedValue({ message: { production_units: ['Kitchen - 三友寿司'] } });
    expect(await getProductionUnitsForBranch()).toEqual(['Kitchen - 三友寿司']);
    expect(get).toHaveBeenCalledWith('ury.ury_pos.api.get_production_units_for_branch');
  });

  it('returns an empty list when the branch has no production units', async () => {
    get.mockResolvedValue({ message: { production_units: [] } });
    expect(await getProductionUnitsForBranch()).toEqual([]);
  });

  it('returns an empty list when the response has no message', async () => {
    get.mockResolvedValue({});
    expect(await getProductionUnitsForBranch()).toEqual([]);
  });

  it('returns an empty list when the request fails', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    get.mockRejectedValue(new Error('417'));
    expect(await getProductionUnitsForBranch()).toEqual([]);
    error.mockRestore();
  });
});
