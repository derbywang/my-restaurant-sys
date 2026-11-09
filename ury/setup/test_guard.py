"""Guards of the test site: an automatic backup before the tests, and a check that the tests leave the roles,
permissions and accounts of the site as they found them.

Why: saving a User or a Role, or changing a permission, can commit, so the rollback at the end of a test class does
not always undo it. Three times (2026-11) a test changed the real roles or accounts of the test site without anyone
noticing. Now every test class (`URYTestCase`) compares, after its own clean-up, a snapshot of

- Role (desk_access, disabled, home_page, is_custom), User (user_type, enabled, language) and Has Role of users,
- every row of Custom DocPerm and DocPerm (all columns except names and timestamps),
- the shop's configuration: every row of the tables in CONFIG_DOCTYPES (POS Profile, the self ordering profile, the
  restaurant, branch, company, payment accounts, prices, menus, kitchens, print formats, scheduled jobs ...) and the
  fields of the settings in CONFIG_SINGLES, compared by content (so a change that keeps `modified` is found too),
  except the working columns listed in WORKING_COLUMNS (a table's "taken" state is the tests' daily business),

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

# What the tests may not leave changed. A fourth time (2026-11) a test left the default customer of the POS Profile
# changed: the guard only looked at roles and permissions.
CONFIG_DOCTYPES = (
	"Custom Field", "Property Setter",  # an installer that is run by mistake rewrites these (2026-11-09)
	"POS Profile", "POS Payment Method",
	"URY Self Ordering Profile", "URY Age Check Item Group", "URY Ordering Device",
	"URY Restaurant", "Order Type Menu", "Menu for Room",
	"Branch", "URY User", "Company",
	"Mode of Payment", "Mode of Payment Account",
	"Item Group", "Item", "Price List", "Customer",
	"URY Menu", "URY Menu Item", "URY Production Unit", "URY Production Item Groups",
	"URY Table", "URY Room",
	"Print Format", "Scheduled Job Type", "Patch Log",
)
# not watched, on purpose: Item Price (ERPNext's `before_tests` deletes every one at the start of each test run and the
# test site makes them again), and the time stamps of a setting
CONFIG_SINGLES = ("System Settings", "Global Defaults", "Selling Settings", "Stock Settings", "Accounts Settings")
# columns the tests change all the time on purpose (the state of a table while guests sit at it)
WORKING_COLUMNS = {
	"Company": {"total_monthly_sales"},  # every order of a test adds to it
	"URY Table": {
		"occupied", "latest_invoice_time", "merged_with",
		"self_order_open", "self_order_opened_at", "self_order_opened_by", "self_order_opening",
	},
}
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


def _config_rows(doctype):
	if not frappe.db.table_exists(doctype):
		return {}
	skip = _VOLATILE - {"name", "docstatus"} | WORKING_COLUMNS.get(doctype, set())
	columns = [c for c in frappe.db.get_table_columns(doctype) if c not in skip]
	listed = ", ".join(f"`{c}`" for c in columns)
	rows = _rows(f"select {listed} from `tab{doctype}`")
	if "parent" in columns and "parentfield" in columns:
		# the rows of a child table have names made at random, and a save writes them again: what counts is the content
		# (and how many times it is there)
		found, seen = {}, Counter()
		for row in rows:
			content = {c: str(row[c]) for c in columns if c not in ("name", "docstatus")}
			key = f"{content.get('parent')} / {content.get('parentfield')} / " + ", ".join(
				f"{k}={v}" for k, v in content.items() if k not in ("parent", "parentfield", "parenttype") and v != "None"
			)
			seen[key] += 1
			found[f"{key} #{seen[key]}"] = {}
		return found
	return {row["name"]: {c: str(row[c]) for c in columns if c != "name"} for row in rows}


def _config_singles():
	marks = ", ".join(["%s"] * len(CONFIG_SINGLES))
	found = frappe.db.sql(f"select doctype, field, value from `tabSingles` where doctype in ({marks})", CONFIG_SINGLES)
	return {
		f"{doctype}.{field}": {"value": str(value)}
		for doctype, field, value in found
		if field not in ("modified", "creation", "owner", "modified_by")
	}


def config_snapshot():
	snapshot = {doctype: _config_rows(doctype) for doctype in CONFIG_DOCTYPES}
	snapshot["Settings"] = _config_singles()
	return snapshot


def config_diff(before, after):
	lines = []
	for table in before:
		old, new = before[table], after.get(table, {})
		for name in sorted(set(old) | set(new)):
			if name not in new:
				lines.append(f"{table} {name}: removed")
			elif name not in old:
				lines.append(f"{table} {name}: added")
			elif old[name] != new[name]:
				changed = {k: (old[name][k], new[name].get(k)) for k in old[name] if old[name][k] != new[name].get(k)}
				lines.append(f"{table} {name}: {changed}")
	return lines


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
	snapshot["_config"] = config_snapshot()
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
	lines += config_diff(before["_config"], after["_config"])
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
			f"{name} changed the roles, accounts, permissions or configuration of the test site (restore them; the backup made "
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
