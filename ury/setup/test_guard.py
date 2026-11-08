"""Guards of the test site: an automatic backup before the tests, and a check that the tests leave the roles,
permissions and accounts of the site as they found them.

Why: saving a User or a Role, or changing a permission, can commit, so the rollback at the end of a test class does
not always undo it. Three times (2026-11) a test changed the real roles or accounts of the test site without anyone
noticing. Now every test class (`URYTestCase`) compares, after its own clean-up, a snapshot of

- Role (desk_access, disabled, home_page, is_custom), User (user_type, enabled, language) and Has Role of users,
- every row of Custom DocPerm and DocPerm (all columns except names and timestamps),

taken before and after; a difference is an error that lists it. And the first test class of a test run makes a backup
of the site (if there is none from the last 30 minutes); only the backups made here are deleted again, the newest
KEEP_AUTO_BACKUPS stay. Backups made by hand are never touched.
"""

import json
import os
import time
from collections import Counter

import frappe

KEEP_AUTO_BACKUPS = 10
BACKUP_EVERY_HOURS = 0.5
MANIFEST = "auto-test-backups.json"

_VOLATILE = {"name", "creation", "modified", "modified_by", "owner", "idx", "docstatus"}
_checked_backup = False


def _rows(sql):
	return frappe.db.sql(sql, as_dict=True)


def _keyed(doctype, columns):
	cols = ", ".join(f"`{c}`" for c in ("name", *columns))
	return {row["name"]: {c: row[c] for c in columns} for row in _rows(f"select {cols} from `tab{doctype}`")}


def _perm_rows(doctype):
	columns = [c for c in frappe.db.get_table_columns(doctype) if c not in _VOLATILE]
	listed = ", ".join(f"`{c}`" for c in columns)
	return Counter(tuple(row[c] for c in columns) for row in _rows(f"select {listed} from `tab{doctype}`")), columns


def access_snapshot():
	"""The roles, accounts and permissions of the site as they are now (committed state)."""
	snapshot = {
		"Role": _keyed("Role", ("desk_access", "disabled", "home_page", "is_custom")),
		"User": _keyed("User", ("user_type", "enabled", "language")),
		"Has Role (users)": Counter(
			(row["parent"], row["role"]) for row in _rows("select parent, role from `tabHas Role` where parenttype = 'User'")
		),
	}
	snapshot["_columns"] = {}
	for doctype in ("Custom DocPerm", "DocPerm"):
		snapshot[doctype], snapshot["_columns"][doctype] = _perm_rows(doctype)
	return snapshot


def access_diff(before, after):
	"""What changed, one line each (empty when nothing)."""
	lines = []
	for label in ("Role", "User"):
		for name in sorted(set(before[label]) | set(after[label])):
			if name not in after[label]:
				lines.append(f"{label} {name}: removed")
			elif name not in before[label]:
				lines.append(f"{label} {name}: added {after[label][name]}")
			elif before[label][name] != after[label][name]:
				changed = {k: (before[label][name][k], after[label][name][k]) for k in before[label][name] if before[label][name][k] != after[label][name][k]}
				lines.append(f"{label} {name}: {changed}")
	lines += _counter_diff("Has Role (users)", before, after, None)
	for doctype in ("Custom DocPerm", "DocPerm"):
		lines += _counter_diff(doctype, before, after, after["_columns"][doctype])
	return lines


def _counter_diff(label, before, after, columns):
	def show(row):
		return dict(zip(columns, row)) if columns else row

	lines = [f"{label}: removed {show(row)}" for row in sorted((before[label] - after[label]).elements(), key=repr)]
	lines += [f"{label}: added {show(row)}" for row in sorted((after[label] - before[label]).elements(), key=repr)]
	return lines


def check_unchanged(name, before):
	"""Class clean-up: the tests of `name` must leave the access data as it was."""
	lines = access_diff(before, access_snapshot())
	if lines:
		shown = "\n  ".join(lines[:40]) + (f"\n  ... and {len(lines) - 40} more" if len(lines) > 40 else "")
		raise AssertionError(
			f"{name} changed the roles, accounts or permissions of the test site (restore them; the backup made "
			f"before this test run is in sites/{frappe.local.site}/private/backups):\n  {shown}"
		)


# --- backups ---------------------------------------------------------------------------
def _backup_dir():
	return frappe.get_site_path("private", "backups")


def _prefix(path):
	return os.path.basename(path).split("-database")[0].split("-site_config")[0].split("-files")[0].split("-private-files")[0]


def ensure_recent_backup():
	"""Once per test run: back up the site unless a backup of the last 30 minutes exists; trim the automatic ones."""
	global _checked_backup
	if _checked_backup:
		return
	_checked_backup = True
	from frappe.utils.backups import new_backup

	folder = _backup_dir()
	os.makedirs(folder, exist_ok=True)
	before = set(os.listdir(folder))
	# our own test of "recent" (the file's age): Frappe reads the time in the file name as UTC, and the names carry
	# the site's time, so with Frappe's own test a recent backup is never found
	newest = max((os.path.getmtime(os.path.join(folder, f)) for f in before if f.endswith("-database.sql.gz")), default=0)
	if time.time() - newest < BACKUP_EVERY_HOURS * 3600:
		return
	new_backup(ignore_files=True, force=True)
	made = {_prefix(f) for f in set(os.listdir(folder)) - before if f.endswith(".gz") or f.endswith(".json")}
	if made:
		manifest = os.path.join(folder, MANIFEST)
		listed = json.load(open(manifest)) if os.path.exists(manifest) else []
		listed += sorted(made - set(listed))
		for old in listed[:-KEEP_AUTO_BACKUPS]:
			for f in os.listdir(folder):
				if f.startswith(old + "-") and f != MANIFEST:
					os.remove(os.path.join(folder, f))
		json.dump(listed[-KEEP_AUTO_BACKUPS:], open(manifest, "w"))
