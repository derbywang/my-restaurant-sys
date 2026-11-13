// Run with `yarn test` (node's built-in test runner).
import { test } from "node:test";
import assert from "node:assert/strict";
import { mergeKots, startPolling } from "./kot-refresh.js";

const kot = (name, extra = {}) => ({ name, ...extra });

// --- the list the screen shows and the list the server gives ------------------------------------------------------
test("the same tickets: nothing changes and the cards the screen holds stay the same objects (no flash, overlay kept)", () => {
  const a = kot("A", { isRotated: true });
  const b = kot("B");
  const { kots, changed } = mergeKots([a, b], [kot("A"), kot("B")]);
  assert.equal(changed, false);
  assert.equal(kots[0], a);
  assert.equal(kots[1], b);
  assert.equal(kots[0].isRotated, true);
});

test("a ticket the push missed is added", () => {
  const a = kot("A");
  const { kots, changed } = mergeKots([a], [kot("N"), kot("A")]);
  assert.equal(changed, true);
  assert.deepEqual(kots.map((k) => k.name), ["N", "A"]);
  assert.equal(kots[1], a);
});

test("a ticket the server no longer lists (served or confirmed elsewhere) is dropped", () => {
  const { kots, changed } = mergeKots([kot("A"), kot("B")], [kot("B")]);
  assert.equal(changed, true);
  assert.deepEqual(kots.map((k) => k.name), ["B"]);
});

test("a ticket served here a moment ago and hidden stays hidden until the server stops listing it", () => {
  const a = kot("A", { showDiv: true });
  const { kots } = mergeKots([a], [kot("A")]);
  assert.equal(kots[0].showDiv, true);
});

test("an empty answer from the server is a real answer: the screen empties", () => {
  const { kots, changed } = mergeKots([kot("A")], []);
  assert.equal(changed, true);
  assert.deepEqual(kots, []);
});

test("no answer (undefined, the request failed) changes nothing", () => {
  const current = [kot("A")];
  const { kots, changed } = mergeKots(current, undefined);
  assert.equal(changed, false);
  assert.equal(kots, current);
});

// --- the timer ---------------------------------------------------------------------------------------------------------
function fakeTimers() {
  const timers = { fns: [], cleared: [], setInterval: (fn, ms) => (timers.fns.push({ fn, ms }), timers.fns.length), clearInterval: (id) => timers.cleared.push(id) };
  return timers;
}

test("the task runs every interval, 30 s by default", async () => {
  const timers = fakeTimers();
  let runs = 0;
  startPolling(() => { runs += 1; }, undefined, timers);
  assert.equal(timers.fns[0].ms, 30000);
  await timers.fns[0].fn();
  await timers.fns[0].fn();
  assert.equal(runs, 2);
});

test("stop clears the timer", () => {
  const timers = fakeTimers();
  const stop = startPolling(() => {}, 1000, timers);
  stop();
  assert.deepEqual(timers.cleared, [1]);
});

test("a run that is still going is not started a second time", async () => {
  const timers = fakeTimers();
  let runs = 0;
  let release;
  let hold = true;
  startPolling(() => { runs += 1; return hold ? new Promise((resolve) => (release = resolve)) : undefined; }, 1000, timers);
  const first = timers.fns[0].fn();
  await timers.fns[0].fn();
  assert.equal(runs, 1);
  hold = false;
  release();
  await first;
  await timers.fns[0].fn();
  assert.equal(runs, 2);
});

test("a task that fails does not stop the polling", async () => {
  const timers = fakeTimers();
  let runs = 0;
  startPolling(() => { runs += 1; throw new Error("offline"); }, 1000, timers);
  await timers.fns[0].fn();
  await timers.fns[0].fn();
  assert.equal(runs, 2);
});

test("a tab or screen that cannot be refreshed right now (busy) is skipped", async () => {
  const timers = fakeTimers();
  let runs = 0;
  let busy = true;
  startPolling(() => { runs += 1; }, 1000, { ...timers, isBusy: () => busy });
  await timers.fns[0].fn();
  assert.equal(runs, 0);
  busy = false;
  await timers.fns[0].fn();
  assert.equal(runs, 1);
});
