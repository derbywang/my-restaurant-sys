import { describe, expect, it } from 'vitest';

import { modulePermissionsFrom, NO_MODULE_PERMISSIONS } from './permission';

describe('modulePermissionsFrom', () => {
  it('reads create and write, wrapped or not', () => {
    expect(modulePermissionsFrom({ create: true, write: true })).toEqual({ create: true, write: true });
    expect(modulePermissionsFrom({ message: { create: false, write: true } })).toEqual({ create: false, write: true });
  });

  it('is a no for everything else', () => {
    for (const bad of [{ create: 1, write: 'yes' }, null, undefined, {}, true, 'x']) {
      expect(modulePermissionsFrom(bad)).toEqual(NO_MODULE_PERMISSIONS);
    }
  });
});
