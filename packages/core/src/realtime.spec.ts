import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  SOCKET_RECONNECT_OPTIONS,
  SLOW_RETRY_MS,
  buildSocketUrl,
  keepTryingToConnect,
  type ReconnectableSocket,
} from './realtime';

describe('buildSocketUrl', () => {
  const page = { protocol: 'http:', hostname: 'ury.localhost', port: '8000', siteName: 'ury.localhost' };

  it('uses the socketio port on the development server, like the Frappe desk', () => {
    expect(buildSocketUrl({ ...page, devServer: true, socketioPort: 9000 })).toBe(
      'http://ury.localhost:9000/ury.localhost'
    );
  });

  it('uses the origin of the page when it is not the development server', () => {
    expect(buildSocketUrl({ ...page, devServer: false, socketioPort: 9000 })).toBe(
      'http://ury.localhost:8000/ury.localhost'
    );
  });

  it('uses the origin of the page when the socketio port is unknown', () => {
    expect(buildSocketUrl({ ...page, devServer: true })).toBe('http://ury.localhost:8000/ury.localhost');
  });

  it('has no port in production behind nginx (https, default port)', () => {
    expect(
      buildSocketUrl({ protocol: 'https:', hostname: 'shop.example.com', port: '', siteName: 'shop.example.com', devServer: false, socketioPort: 9000 })
    ).toBe('https://shop.example.com/shop.example.com');
  });

  it('leaves the site name out when it is not known', () => {
    expect(buildSocketUrl({ ...page, siteName: '' })).toBe('http://ury.localhost:8000');
  });
});

type Handler = (...args: unknown[]) => void;

function fakeSocket() {
  const handlers: Record<string, Handler[]> = {};
  const managerHandlers: Record<string, Handler[]> = {};
  const socket = {
    connected: false,
    connect: vi.fn(),
    on(event: string, fn: Handler) {
      (handlers[event] ??= []).push(fn);
    },
    io: {
      attempts: SOCKET_RECONNECT_OPTIONS.reconnectionAttempts as number,
      on(event: string, fn: Handler) {
        (managerHandlers[event] ??= []).push(fn);
      },
      reconnectionAttempts(n: number) {
        this.attempts = n;
      },
    },
  };
  return {
    socket: socket as unknown as ReconnectableSocket & typeof socket,
    emitManager: (event: string) => (managerHandlers[event] ?? []).forEach((fn) => fn()),
    emitSocket: (event: string) => (handlers[event] ?? []).forEach((fn) => fn()),
  };
}

describe('keepTryingToConnect', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('connects 5 times at first, from 2 s up to 30 s apart', () => {
    expect(SOCKET_RECONNECT_OPTIONS).toEqual({
      reconnectionAttempts: 5,
      reconnectionDelay: 2000,
      reconnectionDelayMax: 30000,
    });
  });

  it('tries again every 60 seconds once the attempts are used up', () => {
    const { socket, emitManager } = fakeSocket();
    keepTryingToConnect(socket, { warn: vi.fn() });
    emitManager('reconnect_failed');
    expect(socket.connect).not.toHaveBeenCalled();
    vi.advanceTimersByTime(SLOW_RETRY_MS);
    expect(socket.connect).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(SLOW_RETRY_MS * 2);
    expect(socket.connect).toHaveBeenCalledTimes(3);
  });

  it('warns once when it goes into the 60 second mode, not on every try', () => {
    const { socket, emitManager } = fakeSocket();
    const warn = vi.fn();
    keepTryingToConnect(socket, { warn });
    emitManager('reconnect_failed');
    emitManager('reconnect_failed'); // the try of the slow mode failed too
    emitManager('reconnect_failed');
    vi.advanceTimersByTime(SLOW_RETRY_MS * 3);
    expect(warn).toHaveBeenCalledTimes(1);
  });

  it('makes a single attempt per minute in the slow mode', () => {
    const { socket, emitManager } = fakeSocket();
    keepTryingToConnect(socket, { warn: vi.fn() });
    emitManager('reconnect_failed');
    expect(socket.io.attempts).toBe(1);
  });

  it('goes back to the first mode when the connection comes back, and warns again next time', () => {
    const { socket, emitManager, emitSocket } = fakeSocket();
    const warn = vi.fn();
    keepTryingToConnect(socket, { warn });
    emitManager('reconnect_failed');
    emitSocket('connect');
    expect(socket.io.attempts).toBe(5);
    vi.advanceTimersByTime(SLOW_RETRY_MS * 3);
    expect(socket.connect).not.toHaveBeenCalled();

    emitManager('reconnect_failed');
    expect(warn).toHaveBeenCalledTimes(2);
  });

  it('does not try while it is connected', () => {
    const { socket, emitManager } = fakeSocket();
    keepTryingToConnect(socket, { warn: vi.fn() });
    emitManager('reconnect_failed');
    socket.connected = true;
    vi.advanceTimersByTime(SLOW_RETRY_MS);
    expect(socket.connect).not.toHaveBeenCalled();
  });
});
