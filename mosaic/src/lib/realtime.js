// Where and how the kitchen display connects to Frappe's Socket.IO server.
// A copy of packages/core/src/realtime.ts (mosaic is not a workspace member and cannot import
// @ury/core): keep the two in step. Tests: `yarn test`.

// The same rules as frappe/public/js/frappe/socketio_client.js get_host(): on the development
// server (`window.dev_server`, `bench start`) the Socket.IO server listens on its own port
// (9000); everywhere else (production, behind nginx) it is the origin of the page. The
// connection is namespaced per site.
export function buildSocketUrl({ protocol, hostname, port, siteName, devServer, socketioPort }) {
  let host = `${protocol}//${hostname}`;
  if (devServer && socketioPort) {
    host = `${host}:${socketioPort}`;
  } else if (port) {
    host = `${host}:${port}`;
  }
  return siteName ? `${host}/${siteName}` : host;
}

// Options for io(url, ...): 5 attempts, 2 s apart at first, at most 30 s apart.
export const SOCKET_RECONNECT_OPTIONS = {
  reconnectionAttempts: 5,
  reconnectionDelay: 2000,
  reconnectionDelayMax: 30000,
};

// After the attempts are used up, the connection is tried once this often.
export const SLOW_RETRY_MS = 60000;

// Never give up, but do not flood the console: after the 5 attempts the socket tries once a
// minute (one attempt each time) and warns once. When the connection is back, the first mode
// is restored (and the next outage warns again).
export function keepTryingToConnect(socket, { warn = console.warn } = {}) {
  let timer = null;

  socket.io.on("reconnect_failed", () => {
    if (timer) return; // a try of the slow mode failed: already warned
    warn("Socket connection failed. Real-time updates are off; trying again every 60 seconds.");
    socket.io.reconnectionAttempts(1);
    timer = setInterval(() => {
      if (!socket.connected) socket.connect();
    }, SLOW_RETRY_MS);
  });

  socket.on("connect", () => {
    if (!timer) return;
    clearInterval(timer);
    timer = null;
    socket.io.reconnectionAttempts(SOCKET_RECONNECT_OPTIONS.reconnectionAttempts);
  });
}
