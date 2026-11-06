// Run with `yarn test` (node's built-in test runner).
import { test } from "node:test";
import assert from "node:assert/strict";
import { elapsedLabel, elapsedMinutes } from "./elapsed.js";

const at = (day, time) => new Date(`${day}T${time}`);

test("a ticket of this minute shows 0 : 0", () => {
  assert.equal(elapsedLabel("2026-11-07", "09:30:10", at("2026-11-07", "09:30:40")), "0 : 0");
});

test("a ticket of the same day counts hours and minutes (1 : 5 is one hour and five minutes)", () => {
  assert.equal(elapsedLabel("2026-11-07", "09:00:00", at("2026-11-07", "10:05:30")), "1 : 5");
  assert.equal(elapsedLabel("2026-11-07", "09:00:00", at("2026-11-07", "09:12:00")), "0 : 12");
});

test("a ticket of yesterday evening, seen after midnight, is not negative", () => {
  assert.equal(elapsedLabel("2026-11-06", "23:50:00", at("2026-11-07", "00:10:00")), "0 : 20");
  assert.equal(elapsedLabel("2026-11-06", "18:12:03", at("2026-11-07", "09:00:00")), "14 : 47");
});

test("a ticket of days ago counts the days", () => {
  assert.equal(elapsedLabel("2026-11-05", "12:00:00", at("2026-11-07", "12:30:00")), "48 : 30");
});

test("the time may carry fractions of a second", () => {
  assert.equal(elapsedMinutes("2026-11-07", "09:00:00.456789", at("2026-11-07", "09:03:00")), 3);
});

test("without a date, a time still to come means before midnight", () => {
  assert.equal(elapsedLabel(undefined, "23:50:00", at("2026-11-07", "00:10:00")), "0 : 20");
  assert.equal(elapsedLabel(undefined, "09:00:00", at("2026-11-07", "09:15:00")), "0 : 15");
});

test("a ticket a little ahead of the clock is 0, never negative", () => {
  assert.equal(elapsedLabel("2026-11-07", "09:00:30", at("2026-11-07", "09:00:00")), "0 : 0");
});
