// Run with `yarn test` (node's built-in test runner).
import { test } from "node:test";
import assert from "node:assert/strict";
import { TIME_BLACK, TIME_RED, timeColor } from "./ticket-time.js";

test("a ticket that waited longer than the warning time shows its time in red", () => {
  assert.equal(timeColor("New Order", 20, 15), TIME_RED);
  assert.equal(timeColor("Order Modified", 15, 15), TIME_RED);
  assert.equal(timeColor("Duplicate", 40, 15), TIME_RED);
});

test("a ticket within the warning time is black", () => {
  assert.equal(timeColor("New Order", 14, 15), TIME_BLACK);
  assert.equal(timeColor("New Order", 0, 15), TIME_BLACK);
});

test("a cancel ticket shows how long ago it was made but is never red (red means the kitchen is slow)", () => {
  assert.equal(timeColor("Cancelled", 90, 15), TIME_BLACK);
  assert.equal(timeColor("Partially cancelled", 90, 15), TIME_BLACK);
});

test("without a warning time nothing is red", () => {
  assert.equal(timeColor("New Order", 500, 0), TIME_BLACK);
  assert.equal(timeColor("New Order", 500, null), TIME_BLACK);
  assert.equal(timeColor("New Order", 500, undefined), TIME_BLACK);
});

test("the warning time may come as text", () => {
  assert.equal(timeColor("New Order", 20, "15"), TIME_RED);
});
