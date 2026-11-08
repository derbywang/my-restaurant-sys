"""Read-only checks before a site goes into service: `bench --site <site> execute ury.ury.api.deploy_check.run`.

Returns `[{"check", "ok", "detail"}]`, the failed ones first. It only reads. More checks are listed in
docs/design/ui-todo.md; add them here as functions that return `(ok, detail)` and register them in CHECKS.
"""

import frappe


def staff_in_a_branch():
	"""Every enabled account with a URY role is in the `user` table of some Branch.

	The reminders and the kitchen screen's updates are sent to the accounts of the branch one by one
	(`branch_realtime.publish_to_branch`); an account that is in no Branch table silently receives nothing.
	Administrator and Guest are not staff accounts."""
	staff = set(
		frappe.get_all("Has Role", filters={"parenttype": "User", "role": ("like", "URY %")}, pluck="parent", distinct=True)
	) - set(frappe.STANDARD_USERS)
	enabled = set(frappe.get_all("User", filters={"enabled": 1, "name": ("in", list(staff) or [""])}, pluck="name"))
	listed = set(frappe.get_all("URY User", filters={"parenttype": "Branch"}, pluck="user", distinct=True))
	missing = sorted(enabled - listed)
	if missing:
		return False, "not in the user table of any Branch (they will not get kitchen reminders): " + ", ".join(missing)
	return True, f"{len(enabled)} staff accounts, all in a Branch"


CHECKS = (("staff in a branch", staff_in_a_branch),)


def run():
	results = []
	for name, check in CHECKS:
		ok, detail = check()
		results.append({"check": name, "ok": bool(ok), "detail": detail})
	results.sort(key=lambda r: r["ok"])
	for r in results:
		print(("OK   " if r["ok"] else "FAIL ") + f"{r['check']}: {r['detail']}")
	return results
