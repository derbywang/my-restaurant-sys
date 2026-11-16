// Run with `yarn test`. The same rules as packages/core/src/wake-lock.spec.ts.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createWakeLock } from "./wake-lock.js";

function fakes(supported = true) {
  const listeners = {};
  const sentinels = [];
  const request = async () => {
    request.calls += 1;
    let onRelease = () => {};
    const sentinel = {
      released: false,
      release: async () => {
        sentinel.released = true;
      },
      addEventListener: (_event, f) => {
        onRelease = f;
      },
      fire: () => {
        sentinel.released = true;
        onRelease();
      },
    };
    sentinels.push(sentinel);
    return sentinel;
  };
  request.calls = 0;
  const nav = supported ? { wakeLock: { request } } : {};
  const doc = {
    visibilityState: "visible",
    addEventListener: (event, f) => {
      listeners[event] = f;
    },
    removeEventListener: (event) => {
      delete listeners[event];
    },
  };
  return { nav, doc, request, sentinels, listeners };
}

test("holds a screen lock", async () => {
  const { nav, doc } = fakes();
  const lock = createWakeLock(nav, doc);
  assert.equal(await lock.start(), "held");
});

test("a browser without it is not an error", async () => {
  const { nav, doc } = fakes(false);
  assert.equal(await createWakeLock(nav, doc).start(), "unsupported");
});

test("a refused request is not an error", async () => {
  const { doc } = fakes();
  const nav = { wakeLock: { request: async () => { throw new Error("NotAllowedError"); } } };
  assert.equal(await createWakeLock(nav, doc).start(), "refused");
});

test("takes the lock again when the page comes back, not while it holds it or while hidden", async () => {
  const { nav, doc, request, sentinels, listeners } = fakes();
  const lock = createWakeLock(nav, doc);
  await lock.start();
  await listeners.visibilitychange();
  assert.equal(request.calls, 1);
  sentinels[0].fire();
  assert.equal(lock.state(), "released");
  doc.visibilityState = "hidden";
  await listeners.visibilitychange();
  assert.equal(request.calls, 1);
  doc.visibilityState = "visible";
  await listeners.visibilitychange();
  assert.equal(request.calls, 2);
  assert.equal(lock.state(), "held");
});

test("stop lets go and stops listening", async () => {
  const { nav, doc, sentinels, listeners } = fakes();
  const lock = createWakeLock(nav, doc);
  await lock.start();
  await lock.stop();
  assert.equal(sentinels[0].released, true);
  assert.equal(listeners.visibilitychange, undefined);
});
