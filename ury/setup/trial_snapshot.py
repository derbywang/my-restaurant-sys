"""Used by scripts/trial_run.sh: the guard's snapshot of a trial site before the tests and the comparison after them.

bench --site <trial site> execute ury.setup.trial_snapshot.save --kwargs '{"path": "..."}'
bench --site <trial site> execute ury.setup.trial_snapshot.compare --kwargs '{"path": "..."}'

compare prints one line per difference and "TRIAL CLEAN" when there are none (the script looks for that line).
Only sites whose name starts with "ury-trial-" are accepted.
"""

import pickle

import frappe

from ury.setup.test_guard import access_diff, access_snapshot


def _only_trial_site():
	if not str(frappe.local.site).startswith("ury-trial-"):
		raise frappe.ValidationError(f"{frappe.local.site} is not a trial site (its name must start with ury-trial-)")


def save(path):
	_only_trial_site()
	with open(path, "wb") as f:
		pickle.dump(access_snapshot(), f)
	print("snapshot saved")


def compare(path):
	_only_trial_site()
	with open(path, "rb") as f:
		before = pickle.load(f)
	lines = access_diff(before, access_snapshot())
	for line in lines:
		print("DIFF", line)
	print("TRIAL CLEAN" if not lines else f"TRIAL DIRTY: {len(lines)} differences")
