import { describe, expect, it, vi } from 'vitest';
import { refreshPrintType } from './print-type';

const cached = { name: 'P', print_type: 'socket', print_format: 'F', qz_host: null };

describe('how the register prints is asked again every time the POS opens', () => {
  it('takes the new way when the shop has chosen a printer since the profile was cached', async () => {
    const fetchLimited = vi.fn(async () => ({ print_type: 'server' }));
    const { profile, changed } = await refreshPrintType(cached, fetchLimited);
    expect(changed).toBe(true);
    expect((profile as unknown as { print_type: string }).print_type).toBe('server');
  });

  it('changes only the print type and leaves the rest of the cached profile alone', async () => {
    const { profile } = await refreshPrintType(cached, async () => ({ print_type: 'server', print_format: 'OTHER', qz_host: 'x' }));
    expect(profile).toEqual({ name: 'P', print_type: 'server', print_format: 'F', qz_host: null });
  });

  it('is the same object when nothing changed (no redraw)', async () => {
    const { profile, changed } = await refreshPrintType(cached, async () => ({ print_type: 'socket' }));
    expect(changed).toBe(false);
    expect(profile).toBe(cached);
  });

  it('keeps the cached way when the server cannot be asked or answers nothing', async () => {
    for (const fetchLimited of [
      async () => {
        throw new Error('offline');
      },
      async () => ({}),
      async () => null,
    ]) {
      const { profile, changed } = await refreshPrintType(cached, fetchLimited);
      expect(changed).toBe(false);
      expect(profile).toBe(cached);
    }
  });

  it('a profile that is not cached yet has nothing to refresh', async () => {
    const fetchLimited = vi.fn(async () => ({ print_type: 'server' }));
    const { profile, changed } = await refreshPrintType(null, fetchLimited);
    expect(changed).toBe(false);
    expect(profile).toBeNull();
    expect(fetchLimited).not.toHaveBeenCalled();
  });
});
