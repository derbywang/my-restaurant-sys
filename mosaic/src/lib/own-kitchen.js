// An account of a kitchen screen whose branch has one kitchen (production unit) goes straight to that screen; with more
// than one it chooses on the list. `branchUnits` are the names of the production units of the account's branch.

export function onlyKitchenOf(units, branchUnits) {
  const mine = (units || []).filter((unit) => !unit.disable && (branchUnits || []).includes(unit.name));
  return mine.length === 1 ? mine[0].name : null;
}
