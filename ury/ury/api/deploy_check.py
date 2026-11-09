"""Read-only checks before a site goes into service: `bench --site <site> execute ury.ury.api.deploy_check.run`.

Every check finds nothing, or findings of a level:

  FAIL  must be fixed before the shop opens (the result of the check at deployment must have none)
  WARN  listed for the owner to judge
  INFO  listed to be confirmed by a person (nothing is wrong by itself)

`run()` prints one line for each finding (FAIL first), returns `[{check, ok, level, detail}]` and writes nothing.
`ensure_ok()` is `run()` that raises when there is a FAIL, so the command exits with an error:

    bench --site <site> execute ury.ury.api.deploy_check.ensure_ok

A check is a function that returns a list of `(level, detail)`; register it in CHECKS. The checks of the permissions
read the tables DocPerm and Custom DocPerm themselves (a doctype with a Custom DocPerm ignores its standard ones),
so they do not depend on the user who runs the command.
"""

import base64
import datetime
import json
import os
import re
import time

import frappe
from frappe.utils import add_to_date, now_datetime

FAIL, WARN, INFO = "FAIL", "WARN", "INFO"
STAFF_ROLES = ("URY Captain", "URY Cashier")
REPORT_ROLES = {"URY Manager", "URY Admin", "System Manager"}
BACKUP_HOURS = 24
ERROR_LOG_HOURS = 24
URY_JOBS = (
	"ury.ury.api.self_ordering.delete_old_sessions",
	"ury.ury.api.ury_kot_validation.kotValidationThread",
)
KNOWN_ERROR_TITLES = ("KOT Error", "Print Fail", "URY Setup Error", "Bill Merge Error", "KOT Error Log")


# --- helpers ----------------------------------------------------------------------------------------------


def _staff_users(roles=None, enabled=True):
	"""Accounts (not Administrator or Guest) that hold one of `roles`, default any URY role."""
	filters = {"parenttype": "User", "role": ("in", list(roles))} if roles else {"parenttype": "User", "role": ("like", "URY %")}
	names = set(frappe.get_all("Has Role", filters=filters, pluck="parent", distinct=True)) - set(frappe.STANDARD_USERS)
	if enabled and names:
		names = set(frappe.get_all("User", filters={"enabled": 1, "name": ("in", list(names))}, pluck="name"))
	return sorted(names)


def _roles_of(user):
	return set(frappe.get_all("Has Role", filters={"parenttype": "User", "parent": user}, pluck="role"))


def _effective_rows(doctype):
	"""The permission rows of a doctype: its Custom DocPerm if it has any, else its standard DocPerm."""
	rows = frappe.get_all("Custom DocPerm", filters={"parent": doctype}, fields=["*"])
	if rows:
		return rows
	return frappe.get_all("DocPerm", filters={"parent": doctype}, fields=["*"])


def _roles_with(doctype, ptype):
	return {r.role for r in _effective_rows(doctype) if r.get(ptype) and not r.get("permlevel")}


def _doctypes_where(role, ptype):
	"""The doctypes a role has `ptype` on (a doctype with a Custom DocPerm uses only those)."""
	custom_parents = set(frappe.get_all("Custom DocPerm", pluck="parent", distinct=True))
	found = set(frappe.get_all("Custom DocPerm", filters={"role": role, ptype: 1, "permlevel": 0}, pluck="parent"))
	for parent in frappe.get_all("DocPerm", filters={"role": role, ptype: 1, "permlevel": 0}, pluck="parent"):
		if parent not in custom_parents:
			found.add(parent)
	return sorted(found)


def _ury_pos_profiles():
	if not frappe.db.has_column("POS Profile", "restaurant"):
		return []
	return frappe.get_all(
		"POS Profile",
		filters={"restaurant": ("is", "set"), "disabled": 0},
		fields=["name", "company", "customer", "selling_price_list", "restaurant", "qz_print", "qz_host", "custom_tax_rounding"],
	)


def _profiles():
	return frappe.get_all("URY Self Ordering Profile", filters={"enabled": 1}, pluck="name")


def _restaurants():
	return frappe.get_all("URY Restaurant", fields=["name", "branch", "active_menu", "company"])


# --- A. accounts and permissions ----------------------------------------------------------------------------


def staff_in_a_branch():
	"""Every enabled account with a URY role is in the `user` table of some Branch.

	The reminders and the kitchen screen's updates are sent to the accounts of the branch one by one
	(`branch_realtime.publish_to_branch`); an account that is in no Branch table silently receives nothing.
	Administrator and Guest are not staff accounts."""
	enabled = set(_staff_users())
	listed = set(frappe.get_all("URY User", filters={"parenttype": "Branch"}, pluck="user", distinct=True))
	missing = sorted(enabled - listed)
	if missing:
		return False, "not in the user table of any Branch (they will not get kitchen reminders): " + ", ".join(missing)
	return True, f"{len(enabled)} staff accounts, all in a Branch"


def _check_staff_in_a_branch():
	ok, detail = staff_in_a_branch()
	return [] if ok else [(FAIL, detail)]


def _check_role_on_accounts(role, label):
	"""Accounts that hold `role`: the cashier and the captain must not (FAIL), the others are listed (WARN)."""
	holders = set(_staff_users([role]))
	if not holders:
		return []
	staff = set(_staff_users(STAFF_ROLES))
	bad, other = sorted(holders & staff), sorted(holders - staff)
	found = []
	if bad:
		found.append((FAIL, f"{label}: held by staff accounts (URY Captain / URY Cashier): " + ", ".join(bad)))
	if other:
		found.append((WARN, f"{label}: held by " + ", ".join(other) + " (is it meant?)"))
	return found


def _check_system_manager():
	return _check_role_on_accounts("System Manager", "System Manager")


def _check_self_ordering_manager():
	return _check_role_on_accounts("Self Ordering Manager", "Self Ordering Manager")


def _check_report_settings():
	if not frappe.db.exists("DocType", "URY Report Settings"):
		return []
	extra = sorted(_roles_with("URY Report Settings", "read") - REPORT_ROLES)
	if extra:
		return [(FAIL, "these roles can read URY Report Settings (that is every report): " + ", ".join(extra))]
	return []


def _check_export():
	found = []
	for role in STAFF_ROLES:
		doctypes = _doctypes_where(role, "export")
		if doctypes:
			found.append((FAIL, f"{role} can export: " + ", ".join(doctypes)))
	return found


def _check_pos_invoice_permissions():
	cancel = _roles_with("POS Invoice", "cancel")
	found = []
	if "URY Captain" in cancel:
		found.append((FAIL, "URY Captain can cancel POS Invoice"))
	missing = [role for role in ("URY Cashier", "URY Manager", "URY Admin") if frappe.db.exists("Role", role) and role not in cancel]
	if missing:
		found.append((FAIL, "cannot cancel POS Invoice (they should): " + ", ".join(missing)))
	return found


def _check_staff_without_desk():
	found = []
	for role in STAFF_ROLES:
		if not frappe.db.exists("Role", role):
			continue
		access, home = frappe.db.get_value("Role", role, ["desk_access", "home_page"])
		if access:
			found.append((FAIL, f"{role} has Desk access (the staff work in the POS)"))
		if home != "pos":
			found.append((FAIL, f"{role} home page is {home!r}, not 'pos'"))
	desk_roles = set(frappe.get_all("Role", filters={"desk_access": 1}, pluck="name")) - {"Desk User"}
	wrong = []
	for user in _staff_users(STAFF_ROLES):
		if not (_roles_of(user) & desk_roles) and frappe.db.get_value("User", user, "user_type") != "Website User":
			wrong.append(user)
	if wrong:
		found.append((FAIL, "staff accounts without a Desk role that are not Website Users: " + ", ".join(wrong)))
	return found


def _check_staff_language():
	wrong = [
		f"{user} ({frappe.db.get_value('User', user, 'language') or 'not set'})"
		for user in _staff_users()
		if frappe.db.get_value("User", user, "language") != "ja"
	]
	return [(WARN, "staff accounts whose language is not ja: " + ", ".join(wrong))] if wrong else []


def _check_ury_kot_permissions():
	rows = frappe.get_all("Custom DocPerm", filters={"parent": "URY KOT"}, fields=["*"])
	if not rows:
		return []
	path = frappe.get_app_path("ury", "ury", "doctype", "ury_kot", "ury_kot.json")
	with open(path, encoding="utf-8") as f:
		standard = json.load(f)["permissions"]
	flags = ("read", "write", "create", "delete", "submit", "cancel", "amend", "print", "email", "report", "share", "export")

	def key(row):
		return (row.get("role"), row.get("permlevel") or 0, tuple(int(bool(row.get(flag))) for flag in flags))

	if sorted(key(r) for r in rows) == sorted(key(p) for p in standard):
		return []
	return [(FAIL, "URY KOT has a Custom DocPerm that differs from ury_kot.json (changes of the JSON do not reach it)")]


# --- B. self ordering and devices ------------------------------------------------------------------------


def _check_devices():
	from ury.ury.api.self_ordering import _device_configuration_error

	found = []
	for device in frappe.get_all("URY Ordering Device", filters={"enabled": 1}, pluck="name"):
		doc = frappe.get_doc("URY Ordering Device", device)
		profile = frappe.get_doc("URY Self Ordering Profile", doc.ordering_profile)
		code = _device_configuration_error(doc, profile)
		if code:
			found.append((FAIL, f"device {device}: {code}"))
	return found


def _sample_token_verifies(profile_name):
	"""A token made the way the server makes it is accepted by the check the guests' pages go through."""
	from ury.ury.api import self_ordering as so

	secret = frappe.utils.password.get_decrypted_password(
		"URY Self Ordering Profile", profile_name, "qr_signing_secret", raise_exception=False
	)
	if not secret:
		return False, "the QR signing secret is empty"
	branch = frappe.db.get_value("URY Self Ordering Profile", profile_name, "branch")
	table = frappe.db.get_value("URY Table", {"branch": branch}, "name")
	if not table:
		return True, ""
	payload = f"{profile_name}|{table}"
	token = base64.urlsafe_b64encode(f"{payload}|{so._sign(payload, secret)}".encode()).decode().rstrip("=")
	try:
		_profile, found, source = so._verify_qr_token(token)
	except Exception:
		frappe.clear_messages()
		return False, "a token signed with the secret is not accepted"
	return (found == table and source == "QR Table"), "a token signed with the secret is not accepted"


def _check_self_ordering_profiles():
	found = []
	for name in _profiles():
		profile = frappe.get_doc("URY Self Ordering Profile", name)
		if not (profile.public_url or "").strip():
			found.append((FAIL, f"{name}: the public address (public_url) is not set"))
		if profile.enable_qr_table_ordering:
			ok, why = _sample_token_verifies(name)
			if not ok:
				found.append((FAIL, f"{name}: {why}"))
	return found


def _check_pickup_and_age():
	found = []
	for name in _profiles():
		profile = frappe.get_doc("URY Self Ordering Profile", name)
		if profile.enable_qr_pickup_ordering:
			found.append((FAIL, f"{name}: pickup ordering is on (the guests' menu does not follow the order type)"))
		groups = [row.item_group for row in profile.get("age_check_item_groups") or []]
		if not groups:
			found.append((FAIL, f"{name}: age_check_item_groups is empty (alcohol is ordered without the age question)"))
		else:
			found.append((INFO, f"{name}: the age question is asked for: " + ", ".join(groups) + " (do they cover every alcohol?)"))
	return found


def _check_default_customers():
	found = []
	for name in _profiles():
		customer = frappe.db.get_value("URY Self Ordering Profile", name, "default_customer")
		if not customer or not frappe.db.exists("Customer", customer):
			found.append((FAIL, f"{name}: the default customer {customer!r} does not exist"))
	for profile in _ury_pos_profiles():
		if not profile.customer or not frappe.db.exists("Customer", profile.customer):
			found.append((FAIL, f"POS Profile {profile.name}: the default customer {profile.customer!r} does not exist"))
	return found


# --- C. kitchen and menu ------------------------------------------------------------------------------------


def _menu_items(menu):
	return frappe.get_all("URY Menu Item", filters={"parent": menu, "disabled": 0}, pluck="item")


def _check_items_without_kitchen():
	from ury.ury.api.kitchen_check import items_without_kitchen

	found = []
	for menu in frappe.get_all("URY Menu", filters={"enabled": 1}, fields=["name", "branch"]):
		for row in items_without_kitchen(menu.branch, _menu_items(menu.name)):
			found.append((FAIL, f"menu {menu.name}: {row['item_name']} ({row['item_group']}) has no kitchen"))
	return found


def _check_restaurants_and_kitchens():
	found = []
	for restaurant in _restaurants():
		if not restaurant.active_menu or not frappe.db.exists("URY Menu", restaurant.active_menu):
			found.append((FAIL, f"restaurant {restaurant.name}: no active menu"))
		if restaurant.branch and not frappe.db.exists("URY Production Unit", {"branch": restaurant.branch}):
			found.append((FAIL, f"branch {restaurant.branch}: no production unit (no kitchen)"))
	return found


def _check_menu_prices():
	found = []
	for restaurant in _restaurants():
		if not restaurant.active_menu or not frappe.db.exists("URY Menu", restaurant.active_menu):
			continue
		price_list = frappe.db.get_value("URY Menu", restaurant.active_menu, "price_list")
		priced = set(frappe.get_all("Item Price", filters={"price_list": price_list}, pluck="item_code"))
		for item in _menu_items(restaurant.active_menu):
			if item not in priced:
				found.append((FAIL, f"menu {restaurant.active_menu}: {item} has no price in {price_list} (No item price found)"))
	return found


def _check_not_for_self_ordering():
	found = []
	if not frappe.db.has_column("URY Menu Item", "self_order_allowed"):
		return found
	for restaurant in _restaurants():
		if not restaurant.active_menu:
			continue
		off = frappe.get_all(
			"URY Menu Item", filters={"parent": restaurant.active_menu, "disabled": 0, "self_order_allowed": 0}, pluck="item"
		)
		if off:
			found.append((WARN, f"menu {restaurant.active_menu}: not for self ordering: " + ", ".join(sorted(off))))
	return found


# --- D. site, Japan and payment ------------------------------------------------------------------------------


def _check_site_settings():
	found = []
	wanted = {
		"time zone": (frappe.db.get_single_value("System Settings", "time_zone"), "Asia/Tokyo"),
		"language": (frappe.db.get_single_value("System Settings", "language"), "ja"),
		"country": (frappe.db.get_single_value("System Settings", "country"), "Japan"),
		"currency": (frappe.db.get_single_value("Global Defaults", "default_currency"), "JPY"),
	}
	for label, (have, want) in wanted.items():
		if have != want:
			found.append((FAIL, f"{label} is {have!r}, should be {want!r}"))
	return found


def _check_tax_id():
	found = []
	for company in {r.company for r in _restaurants() if r.company}:
		tax_id = frappe.db.get_value("Company", company, "tax_id") or ""
		if not re.fullmatch(r"T\d{13}", tax_id.strip()):
			found.append((WARN, f"company {company}: the registration number (tax_id) is {tax_id!r}, not T + 13 digits"))
	return found


def _check_receipt_format():
	from ury.setup.jp_tax import RECEIPT_FORMAT

	html = frappe.db.get_value("Print Format", RECEIPT_FORMAT, "html") if frappe.db.exists("Print Format", RECEIPT_FORMAT) else None
	if html is None:
		return [(FAIL, f"the print format {RECEIPT_FORMAT} does not exist")]
	with open(frappe.get_app_path("ury", "templates", "print_formats", "ury_jp_receipt.html"), encoding="utf-8") as f:
		if f.read() != html:
			return [(FAIL, f"the print format {RECEIPT_FORMAT} differs from the template file (migrate writes it back)")]
	return []


def _check_payment_accounts():
	found = []
	for profile in _ury_pos_profiles():
		for row in frappe.get_all("POS Payment Method", filters={"parent": profile.name}, pluck="mode_of_payment"):
			account = frappe.db.get_value(
				"Mode of Payment Account", {"parent": row, "company": profile.company}, "default_account"
			)
			if not account:
				found.append((FAIL, f"{profile.name}: the payment method {row} has no default account for {profile.company}"))
	return found


def _check_print_settings():
	found = []
	for profile in _ury_pos_profiles():
		if profile.qz_print and not profile.qz_host:
			found.append((WARN, f"POS Profile {profile.name}: QZ printing is on but qz_host is empty"))
		if not profile.custom_tax_rounding:
			found.append((WARN, f"POS Profile {profile.name}: the tax rounding (custom_tax_rounding) is not set"))
	return found


def _qz_paired(key_pem, cert_pem):
	from cryptography import x509
	from cryptography.hazmat.primitives import hashes, serialization
	from cryptography.hazmat.primitives.asymmetric import padding

	key = serialization.load_pem_private_key(key_pem, password=None)
	cert = x509.load_pem_x509_certificate(cert_pem)
	message = b"deploy_check"
	signature = key.sign(message, padding.PKCS1v15(), hashes.SHA512())
	cert.public_key().verify(signature, message, padding.PKCS1v15(), hashes.SHA512())


def _check_qz_keys():
	from ury.ury.api.ury_print import _read_private_file

	uses_qz = any(p.qz_print for p in _ury_pos_profiles())
	conf = frappe.get_site_config()
	if not (conf.get("qz_private_key") or conf.get("qz_certificate_file")):
		return [(FAIL if uses_qz else WARN, "the QZ private key and certificate are not set in site_config (qz_private_key, qz_certificate_file)")]
	level = FAIL if uses_qz else WARN
	try:
		key = _read_private_file("qz_private_key", "QZ private key")
		cert = _read_private_file("qz_certificate_file", "QZ certificate")
	except Exception as e:
		frappe.clear_messages()
		return [(level, f"the QZ key or certificate cannot be read: {e}")]
	try:
		_qz_paired(key, cert)
	except Exception:
		return [(level, "the QZ private key and certificate are not a pair")]
	return []


def _check_realtime_config():
	found = []
	for key in ("socketio_port", "webserver_host"):
		if not frappe.conf.get(key):
			found.append((WARN, f"{key} is not set in common_site_config.json (realtime messages)"))
	return found


def _check_encryption_key():
	return [] if frappe.conf.get("encryption_key") else [(FAIL, "encryption_key is not in site_config.json (encrypted fields cannot be read)")]


def _check_allow_tests():
	return [(WARN, "allow_tests is on (not for a shop's site)")] if frappe.conf.get("allow_tests") else []


# --- E. running state ----------------------------------------------------------------------------------------


def _check_scheduler():
	from frappe.utils.scheduler import is_scheduler_disabled

	found = []
	if is_scheduler_disabled(verbose=False):
		found.append((FAIL, "the scheduler is disabled (old sessions are not cleared, the kitchen ticket check does not run)"))
	for method in URY_JOBS:
		row = frappe.db.get_value("Scheduled Job Type", {"method": method}, ["name", "stopped"], as_dict=True)
		if not row:
			found.append((FAIL, f"the scheduled job {method} is not registered (migrate registers it)"))
		elif row.stopped:
			found.append((FAIL, f"the scheduled job {method} is stopped"))
	return found


def _check_backups():
	folder = frappe.get_site_path("private", "backups")
	limit = time.time() - BACKUP_HOURS * 3600
	if os.path.isdir(folder) and any(os.path.getmtime(os.path.join(folder, f)) >= limit for f in os.listdir(folder)):
		return []
	return [(WARN, f"no backup file in the last {BACKUP_HOURS} hours")]


def _seconds(value):
	if isinstance(value, str):
		value = datetime.datetime.fromisoformat(value)
	return value.replace(microsecond=0)


def pending_patches():
	from frappe.modules.patch_handler import get_all_patches

	done = set(frappe.get_all("Patch Log", pluck="patch"))
	return [p for p in get_all_patches() if p not in done]


def doctypes_out_of_date(app="ury"):
	"""[(doctype, why)]: the JSON file is newer than the database (compared by the second: the file keeps fractions of a
	second that the database column does not), or a field has no column."""
	from frappe.model import data_fieldtypes

	modules = [m.strip() for m in open(frappe.get_app_path(app, "modules.txt"), encoding="utf-8").read().splitlines() if m.strip()]
	found = []
	for module in modules:
		module_folder = frappe.scrub(module)
		doctype_folder = frappe.get_app_path(app, module_folder, "doctype")
		if not os.path.isdir(doctype_folder):
			continue
		for folder in sorted(os.listdir(doctype_folder)):
			path = os.path.join(doctype_folder, folder, f"{folder}.json")
			if not os.path.isfile(path):
				continue
			with open(path, encoding="utf-8") as f:
				spec = json.load(f)
			name = spec["name"]
			if not frappe.db.exists("DocType", name):
				found.append((name, "not in the database"))
				continue
			file_modified = _seconds(spec["modified"])
			db_modified = _seconds(frappe.db.get_value("DocType", name, "modified"))
			if file_modified > db_modified:
				found.append((name, f"the file is newer ({file_modified} > {db_modified})"))
			if spec.get("issingle"):
				continue
			missing = [
				field["fieldname"]
				for field in spec.get("fields", [])
				if field.get("fieldtype") in data_fieldtypes and not frappe.db.has_column(name, field["fieldname"])
			]
			if missing:
				found.append((name, "no column for " + ", ".join(missing)))
	return found


def _check_migrated():
	found = []
	patches = pending_patches()
	if patches:
		found.append((FAIL, f"{len(patches)} patches are not run (migrate): " + ", ".join(patches[:8]) + (" ..." if len(patches) > 8 else "")))
	for name, why in doctypes_out_of_date():
		found.append((FAIL, f"DocType {name} is not synced: {why}"))
	return found


def _check_error_log():
	since = add_to_date(now_datetime(), hours=-ERROR_LOG_HOURS)
	rows = frappe.get_all(
		"Error Log",
		filters={"creation": (">=", since)},
		or_filters=[["method", "in", list(KNOWN_ERROR_TITLES)], ["method", "like", "%URY%"], ["error", "like", "%/apps/ury/%"]],
		pluck="method",
	)
	if not rows:
		return []
	counts = {}
	for title in rows:
		counts[title] = counts.get(title, 0) + 1
	return [(WARN, f"Error Log in the last {ERROR_LOG_HOURS} hours: " + ", ".join(f"{t} x{c}" for t, c in sorted(counts.items())))]


def _open_shifts():
	return frappe.get_all("POS Opening Entry", filters={"status": "Open", "docstatus": 1}, pluck="name")


def _check_leftovers():
	found = []
	users = [
		u
		for u in frappe.get_all(
			"User",
			filters={"enabled": 1},
			or_filters=[["name", "like", "%@example.com"], ["name", "like", "%test%"]],
			pluck="name",
		)
		if u not in frappe.STANDARD_USERS
	]
	if users:
		found.append((WARN, "accounts that look like test accounts: " + ", ".join(sorted(users))))
	if not _open_shifts():
		drafts = frappe.get_all("POS Invoice", filters={"docstatus": 0}, pluck="name")
		if drafts:
			found.append((WARN, f"{len(drafts)} unpaid orders and no open shift: " + ", ".join(sorted(drafts)[:8])))
	return found


def _check_open_shifts():
	shifts = _open_shifts()
	return [(WARN, "open shifts (left from testing?): " + ", ".join(shifts))] if shifts else []


# --- the list ------------------------------------------------------------------------------------------------

CHECKS = (
	("staff in a branch", _check_staff_in_a_branch),
	("System Manager on accounts", _check_system_manager),
	("Self Ordering Manager on accounts", _check_self_ordering_manager),
	("who reads the reports", _check_report_settings),
	("export permission of the staff", _check_export),
	("POS Invoice permissions", _check_pos_invoice_permissions),
	("staff without Desk", _check_staff_without_desk),
	("language of the staff", _check_staff_language),
	("URY KOT permissions", _check_ury_kot_permissions),
	("tablets", _check_devices),
	("self ordering profile", _check_self_ordering_profiles),
	("pickup and the age question", _check_pickup_and_age),
	("default customers", _check_default_customers),
	("dishes without a kitchen", _check_items_without_kitchen),
	("restaurants and kitchens", _check_restaurants_and_kitchens),
	("dishes without a price", _check_menu_prices),
	("dishes not for self ordering", _check_not_for_self_ordering),
	("site settings", _check_site_settings),
	("registration number", _check_tax_id),
	("receipt format", _check_receipt_format),
	("payment method accounts", _check_payment_accounts),
	("POS Profile print settings", _check_print_settings),
	("QZ key and certificate", _check_qz_keys),
	("realtime configuration", _check_realtime_config),
	("encryption key", _check_encryption_key),
	("allow_tests", _check_allow_tests),
	("scheduler and jobs", _check_scheduler),
	("backups", _check_backups),
	("patches and doctypes", _check_migrated),
	("error log", _check_error_log),
	("test leftovers", _check_leftovers),
	("open shifts", _check_open_shifts),
)

ORDER = {FAIL: 0, WARN: 1, INFO: 2, "OK": 3}


def run():
	results = []
	for name, check in CHECKS:
		findings = check()
		if not findings:
			results.append({"check": name, "ok": True, "level": "OK", "detail": "OK"})
		for level, detail in findings:
			results.append({"check": name, "ok": level == INFO, "level": level, "detail": detail})
	results.sort(key=lambda r: ORDER[r["level"]])
	for r in results:
		print(f"{r['level']:<5}{r['check']}: {r['detail']}")
	fails = sum(r["level"] == FAIL for r in results)
	warns = sum(r["level"] == WARN for r in results)
	print(f"{fails} failed, {warns} warnings")
	return results


def ensure_ok():
	"""`run()` that raises when a check failed, so the command exits with an error (for the deployment script)."""
	results = run()
	if any(r["level"] == FAIL for r in results):
		frappe.throw("deploy_check: " + ", ".join(sorted({r["check"] for r in results if r["level"] == FAIL})))
	return results
