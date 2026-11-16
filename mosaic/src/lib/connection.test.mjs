// Run with `yarn test` (node's built-in test runner). The same rules as packages/core/src/connection.spec.ts.
import { test } from "node:test";
import assert from "node:assert/strict";
import { CHECK_MS, FAILS_BEFORE_OFFLINE, createConnectionMonitor } from "./connection.js";

const sequence = (...answers) => {
  const queue = [...answers];
  const check = async () => {
    check.calls += 1;
    const next = queue.length ? queue.shift() : true;
    if (next === "throw") throw new Error("network");
    return next;
  };
  check.calls = 0;
  return check;
};

test("looks every 15 seconds; two failures in a row are an outage", () => {
  assert.equal(CHECK_MS, 15000);
  assert.equal(FAILS_BEFORE_OFFLINE, 2);
});

test("one failed look is a hiccup, two (a throw counts) are an outage", async () => {
  const changes = [];
  const monitor = createConnectionMonitor({ check: sequence(false, true, false, "throw"), onChange: (o) => changes.push(o) });
  await monitor.tick();
  await monitor.tick();
  assert.deepEqual(changes, []);
  await monitor.tick();
  await monitor.tick();
  assert.deepEqual(changes, [false]);
  assert.equal(monitor.online(), false);
});

test("the first answer after an outage brings it back, once", async () => {
  const changes = [];
  const monitor = createConnectionMonitor({ check: sequence(false, false, true, true), onChange: (o) => changes.push(o) });
  for (let i = 0; i < 4; i++) await monitor.tick();
  assert.deepEqual(changes, [false, true]);
});

test("the browser's offline is believed at once, online asks the server", async () => {
  const changes = [];
  const check = sequence(true);
  const monitor = createConnectionMonitor({ check, onChange: (o) => changes.push(o) });
  monitor.browserOffline();
  assert.deepEqual(changes, [false]);
  await monitor.browserOnline();
  assert.equal(check.calls, 1);
  assert.deepEqual(changes, [false, true]);
});

test("browserOnline with a silent server stays offline", async () => {
  const changes = [];
  const monitor = createConnectionMonitor({ check: sequence(false), onChange: (o) => changes.push(o) });
  monitor.browserOffline();
  await monitor.browserOnline();
  assert.equal(monitor.online(), false);
  assert.deepEqual(changes, [false]);
});
