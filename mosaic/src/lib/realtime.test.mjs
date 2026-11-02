// Run with `yarn test` (node's built-in test runner). The same cases as
// packages/core/src/realtime.spec.ts: this file is the Vue app's copy of those rules.
import { test, mock } from "node:test";
import assert from "node:assert/strict";
import {
  SLOW_RETRY_MS,
  SOCKET_RECONNECT_OPTIONS,
  buildSocketUrl,
  keepTryingToConnect,
} from "./realtime.js";

const page = { protocol: "http:", hostname: "ury.localhost", port: "8000", siteName: "ury.localhost" };

test("the dev server uses the socketio port, like the Frappe desk", () => {
  assert.equal(
    buildSocketUrl({ ...page, devServer: true, socketioPort: 9000 }),
    "http://ury.localhost:9000/ury.localhost"
  );
});

test("without the dev server it is the origin of the page", () => {
  assert.equal(
    buildSocketUrl({ ...page, devServer: false, socketioPort: 9000 }),
    "http://ury.localhost:8000/ury.localhost"
  );
  assert.equal(buildSocketUrl({ ...page, devServer: true }), "http://ury.localhost:8000/ury.localhost");
});

test("production behind nginx has no port", () => {
  assert.equal(
    buildSocketUrl({ protocol: "https:", hostname: "shop.example.com", port: "", siteName: "shop.example.com", devServer: false, socketioPort: 9000 }),
    "https://shop.example.com/shop.example.com"
  );
});

test("the first mode is 5 attempts from 2 s to 30 s", () => {
  assert.deepEqual(SOCKET_RECONNECT_OPTIONS, {
    reconnectionAttempts: 5,
    reconnectionDelay: 2000,
    reconnectionDelayMax: 30000,
  });
});

function fakeSocket() {
  const socketHandlers = {};
  const managerHandlers = {};
  const socket = {
    connected: false,
    connectCalls: 0,
    connect() {
      this.connectCalls += 1;
    },
    on(event, fn) {
      (socketHandlers[event] ??= []).push(fn);
    },
    io: {
      attempts: 5,
      on(event, fn) {
        (managerHandlers[event] ??= []).push(fn);
      },
      reconnectionAttempts(n) {
        this.attempts = n;
      },
    },
  };
  return {
    socket,
    emitManager: (event) => (managerHandlers[event] ?? []).forEach((fn) => fn()),
    emitSocket: (event) => (socketHandlers[event] ?? []).forEach((fn) => fn()),
  };
}

test("it tries every 60 seconds after the attempts are used up, and warns once", () => {
  mock.timers.enable({ apis: ["setInterval"] });
  try {
    const { socket, emitManager } = fakeSocket();
    const warnings = [];
    keepTryingToConnect(socket, { warn: (m) => warnings.push(m) });
    emitManager("reconnect_failed");
    emitManager("reconnect_failed");
    assert.equal(socket.io.attempts, 1);
    assert.equal(socket.connectCalls, 0);
    mock.timers.tick(SLOW_RETRY_MS * 3);
    assert.equal(socket.connectCalls, 3);
    assert.equal(warnings.length, 1);
  } finally {
    mock.timers.reset();
  }
});

test("it goes back to the first mode when the connection is back", () => {
  mock.timers.enable({ apis: ["setInterval"] });
  try {
    const { socket, emitManager, emitSocket } = fakeSocket();
    const warnings = [];
    keepTryingToConnect(socket, { warn: (m) => warnings.push(m) });
    emitManager("reconnect_failed");
    emitSocket("connect");
    assert.equal(socket.io.attempts, 5);
    mock.timers.tick(SLOW_RETRY_MS * 3);
    assert.equal(socket.connectCalls, 0);
    emitManager("reconnect_failed");
    assert.equal(warnings.length, 2);
  } finally {
    mock.timers.reset();
  }
});

test("it does not try while connected", () => {
  mock.timers.enable({ apis: ["setInterval"] });
  try {
    const { socket, emitManager } = fakeSocket();
    keepTryingToConnect(socket, { warn: () => {} });
    emitManager("reconnect_failed");
    socket.connected = true;
    mock.timers.tick(SLOW_RETRY_MS);
    assert.equal(socket.connectCalls, 0);
  } finally {
    mock.timers.reset();
  }
});
