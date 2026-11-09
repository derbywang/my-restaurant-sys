import { beforeEach, describe, expect, it } from 'vitest';

import { useServiceRequestStore } from './service-request-store';

describe('tables version', () => {
  beforeEach(() => {
    useServiceRequestStore.setState({ tablesVersion: 0 });
  });

  it('goes up each time the tables have to be read again (a call, a table that was ordered at, the poll)', () => {
    const { bumpTables } = useServiceRequestStore.getState();
    bumpTables();
    bumpTables();
    expect(useServiceRequestStore.getState().tablesVersion).toBe(2);
  });
});

describe('refresh', () => {
  it('is what the listener registers, so that any screen can ask for the calls again', () => {
    let asked = 0;
    useServiceRequestStore.getState().setRefresh(() => {
      asked += 1;
    });
    useServiceRequestStore.getState().refresh();
    expect(asked).toBe(1);
  });
});
