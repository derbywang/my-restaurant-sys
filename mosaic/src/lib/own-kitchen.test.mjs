// Run with `yarn test` (node's built-in test runner).
import { test } from "node:test";
import assert from "node:assert/strict";
import { onlyKitchenOf } from "./own-kitchen.js";

const unit = (name, disable = 0) => ({ name, disable });

test("one kitchen in the branch: the account goes straight to it", () => {
  assert.equal(onlyKitchenOf([unit("Kitchen - A")], ["Kitchen - A"]), "Kitchen - A");
});

test("two kitchens: the account chooses", () => {
  assert.equal(onlyKitchenOf([unit("Kitchen - A"), unit("Bar - A")], ["Kitchen - A", "Bar - A"]), null);
});

test("kitchens of other branches do not count", () => {
  const units = [unit("Kitchen - A"), unit("Kitchen - B")];
  assert.equal(onlyKitchenOf(units, ["Kitchen - A"]), "Kitchen - A");
});

test("a kitchen that is switched off does not count", () => {
  const units = [unit("Kitchen - A"), unit("Old - A", 1)];
  assert.equal(onlyKitchenOf(units, ["Kitchen - A", "Old - A"]), "Kitchen - A");
  assert.equal(onlyKitchenOf([unit("Old - A", 1)], ["Old - A"]), null);
});

test("an account in no branch, or a branch without kitchens, gets the list", () => {
  assert.equal(onlyKitchenOf([unit("Kitchen - A")], []), null);
  assert.equal(onlyKitchenOf([], ["Kitchen - A"]), null);
  assert.equal(onlyKitchenOf(undefined, undefined), null);
});
