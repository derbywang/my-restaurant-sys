/**
 * Where and how the apps connect to Frappe's Socket.IO server. No dependency on
 * socket.io-client: the apps create the socket, these are the rules they share.
 * (mosaic/src/lib/realtime.js is a copy of the same rules for the Vue app.)
 */

export interface SocketUrlInput {
  protocol: string;
  hostname: string;
  /** `window.location.port`, empty for the default port */
  port: string;
  siteName: string;
  /** `window.dev_server`: true on `bench start` */
  devServer?: boolean;
  /** `frappe.boot.socketio_port` */
  socketioPort?: number | string;
}

/**
 * The same rules as frappe/public/js/frappe/socketio_client.js `get_host()`: on the
 * development server the Socket.IO server listens on its own port (9000), not on the web
 * port; everywhere else (production, behind nginx) it is the origin of the page. The
 * connection is namespaced per site.
 */
export function buildSocketUrl({
  protocol,
  hostname,
  port,
  siteName,
  devServer,
  socketioPort,
}: SocketUrlInput): string {
  let host = `${protocol}//${hostname}`;
  if (devServer && socketioPort) {
    host = `${host}:${socketioPort}`;
  } else if (port) {
    host = `${host}:${port}`;
  }
  return siteName ? `${host}/${siteName}` : host;
}

/** Options for `io(url, ...)`: 5 attempts, 2 s apart at first, at most 30 s apart. */
export const SOCKET_RECONNECT_OPTIONS = {
  reconnectionAttempts: 5,
  reconnectionDelay: 2000,
  reconnectionDelayMax: 30000,
} as const;

/** After the attempts are used up, the connection is tried once this often. */
export const SLOW_RETRY_MS = 60_000;

/** The part of a socket.io-client `Socket` that `keepTryingToConnect` uses. */
export interface ReconnectableSocket {
  connected: boolean;
  connect(): unknown;
  on(event: 'connect', listener: () => void): unknown;
  io: {
    on(event: 'reconnect_failed', listener: () => void): unknown;
    reconnectionAttempts(attempts: number): unknown;
  };
}

/**
 * Never give up, but do not flood the console: after the 5 attempts of
 * SOCKET_RECONNECT_OPTIONS the socket tries once a minute (one attempt each time) and warns
 * once. When the connection is back, the first mode is restored (and the next outage warns
 * again).
 */
export function keepTryingToConnect(
  socket: ReconnectableSocket,
  { warn = console.warn }: { warn?: (message: string) => void } = {}
): void {
  let timer: ReturnType<typeof setInterval> | null = null;

  socket.io.on('reconnect_failed', () => {
    if (timer) return; // a try of the slow mode failed: already warned
    warn(
      'Socket connection failed. Real-time updates are off; trying again every 60 seconds.'
    );
    socket.io.reconnectionAttempts(1);
    timer = setInterval(() => {
      if (!socket.connected) socket.connect();
    }, SLOW_RETRY_MS);
  });

  socket.on('connect', () => {
    if (!timer) return;
    clearInterval(timer);
    timer = null;
    socket.io.reconnectionAttempts(SOCKET_RECONNECT_OPTIONS.reconnectionAttempts);
  });
}
