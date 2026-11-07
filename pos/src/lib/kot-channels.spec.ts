import { describe, expect, it, vi } from 'vitest';
import { kotErrorChannelNames, subscribeKotErrorChannels } from './kot-channels';

function fakeSocket() {
  const handlers = new Map<string, Set<(payload: Record<string, unknown>) => void>>();
  return {
    on: (name: string, fn: (payload: Record<string, unknown>) => void) => {
      if (!handlers.has(name)) handlers.set(name, new Set());
      handlers.get(name)!.add(fn);
    },
    off: (name: string, fn: (payload: Record<string, unknown>) => void) => handlers.get(name)?.delete(fn),
    emit: (name: string, payload: Record<string, unknown>) => handlers.get(name)?.forEach((fn) => fn(payload)),
    names: () => [...handlers.entries()].filter(([, s]) => s.size > 0).map(([n]) => n),
  };
}

describe('kotErrorChannelNames', () => {
  it('keeps a production unit name with spaces and dashes whole', () => {
    expect(kotErrorChannelNames('三友寿司', ['Kitchen - 三友寿司'])).toEqual(['kot_error_三友寿司_Kitchen - 三友寿司']);
  });

  it('keeps a branch name with a space whole', () => {
    expect(kotErrorChannelNames('三友寿司 二号店', ['Kitchen - 三友寿司 二号店'])).toEqual([
      'kot_error_三友寿司 二号店_Kitchen - 三友寿司 二号店',
    ]);
  });

  it('gives one channel per unit, and none without a branch or units', () => {
    expect(kotErrorChannelNames('B', ['A one', 'B two'])).toEqual(['kot_error_B_A one', 'kot_error_B_B two']);
    expect(kotErrorChannelNames('', ['A'])).toEqual([]);
    expect(kotErrorChannelNames('B', [])).toEqual([]);
  });
});

describe('subscribeKotErrorChannels', () => {
  it('listens to the channel the server publishes on and passes the payload on', () => {
    const socket = fakeSocket();
    const handler = vi.fn();
    subscribeKotErrorChannels(socket, '三友寿司', ['Kitchen - 三友寿司'], handler);
    expect(socket.names()).toEqual(['kot_error_三友寿司_Kitchen - 三友寿司']);
    const payload = { kind: 'no_kitchen', items: ['Sake'] };
    socket.emit('kot_error_三友寿司_Kitchen - 三友寿司', payload);
    expect(handler).toHaveBeenCalledWith(payload);
  });

  it('does not hear the pieces of a name split at its spaces', () => {
    const socket = fakeSocket();
    const handler = vi.fn();
    subscribeKotErrorChannels(socket, '三友寿司', ['Kitchen - 三友寿司'], handler);
    socket.emit('kot_error_三友寿司_Kitchen', {});
    expect(handler).not.toHaveBeenCalled();
  });

  it('listens to every unit, and stops when told to', () => {
    const socket = fakeSocket();
    const handler = vi.fn();
    const stop = subscribeKotErrorChannels(socket, 'B', ['A one', 'B two'], handler);
    socket.emit('kot_error_B_A one', {});
    socket.emit('kot_error_B_B two', {});
    expect(handler).toHaveBeenCalledTimes(2);
    stop();
    socket.emit('kot_error_B_A one', {});
    expect(handler).toHaveBeenCalledTimes(2);
    expect(socket.names()).toEqual([]);
  });
});
