"""Who may read the sales figures (2026-11 decision).

Two levels, both decided by DocType permissions, never by a role name:
  A. the POS dashboard (/dashboard): who may settle a bill (submit on POS Invoice): cashier, manager, admin;
     not the captain (waiter). Every function behind that page checks BEFORE it reads its cache.
  B. the report_api reports and the admin app's data: who may read URY Report Settings (the DocType that
     configures the reports): URY Manager, URY Admin, System Manager; not the cashier, not the captain.
Also: the admin app's `get_module_records` reads only nine DocTypes and only the fields its pages show, and the
captain and the cashier no longer export POS Invoices. Run on the test site only.
"""

import ast
import importlib
import importlib.util
import inspect

import frappe
from frappe.utils import get_datetime

from ury.setup.test_site import BRANCH, CAPTAIN, CASHIER, MANAGER, URYTestCase, as_user
from ury.ury.api import dashboard, ury_dashboard, ury_service_line
from ury.ury.api.pos_permissions import get_pos_permissions
from ury.ury.report_api import customers, sales
from ury.ury.report_api.utils import require_manager

ADMIN = "dash-admin@test.local"
SYSTEM_MANAGER = "dash-sm@test.local"
SENSITIVE = "dash-sensitive@test.local"

# the dashboard page of the POS: every function it calls
SALES_VIEW_FUNCTIONS = (
	ury_dashboard.get_dashboard_stats,
	ury_dashboard.get_needs_attention,
	ury_dashboard.get_shift_metrics,
	ury_dashboard.get_baseline,
	ury_dashboard.get_floor_load,
	ury_service_line.get_service_line,
	ury_service_line.get_running_low,
)


def cache_keys(branch):
	now = get_datetime()
	return [
		f"ury_dashboard_stats:{branch}",
		f"ury_dashboard_needs_attention:{branch}",
		f"ury_dashboard_shift_metrics:{branch}",
		f"ury_dashboard_baseline:{branch}:{now.weekday()}:{now.hour}",
		f"ury_dashboard_floor_load:{branch}",
		f"ury_dashboard_service_line:{branch}",
		f"ury_dashboard_running_low:{branch}",
	]


def make_user(email, role):
	if frappe.db.exists("User", email):
		frappe.delete_doc("User", email, force=True, ignore_permissions=True)
	frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": email.split("@")[0],
			"send_welcome_email": 0,
			"enabled": 1,
			"roles": [{"role": role}],
		}
	).insert(ignore_permissions=True)
	frappe.clear_cache(user=email)


class DashboardCase(URYTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# the clean-up is registered first: whatever fails below, the users are removed again
		cls.addClassCleanup(cls._remove_users)
		make_user(ADMIN, "URY Admin")
		make_user(SYSTEM_MANAGER, "System Manager")
		frappe.db.commit()

	@classmethod
	def _remove_users(cls):
		frappe.set_user("Administrator")
		for email in (ADMIN, SYSTEM_MANAGER, SENSITIVE):
			if frappe.db.exists("User", email):
				frappe.delete_doc("User", email, force=True, ignore_permissions=True)
		frappe.db.commit()


class TestSalesViewGate(DashboardCase):
	"""Level A: the POS dashboard."""

	def test_the_captain_is_refused_by_every_function(self):
		for fn in SALES_VIEW_FUNCTIONS:
			with self.subTest(fn=fn.__name__), as_user(CAPTAIN):
				with self.assertRaises(frappe.PermissionError):
					fn(branch=BRANCH)

	def test_cashier_manager_and_admin_may_read(self):
		for user in (CASHIER, MANAGER, ADMIN, "Administrator"):
			for fn in SALES_VIEW_FUNCTIONS:
				with self.subTest(user=user, fn=fn.__name__), as_user(user):
					fn(branch=BRANCH)  # must not raise

	def test_a_filled_cache_does_not_open_the_door(self):
		"""Someone read the figures a moment ago: the cache holds them. The captain still gets nothing."""
		keys = cache_keys(BRANCH)
		self.addCleanup(lambda: [frappe.cache().delete_value(key) for key in keys])
		for key in keys:
			frappe.cache().set_value(key, {"sentinel": 1}, expires_in_sec=60)

		for fn in SALES_VIEW_FUNCTIONS:
			with self.subTest(fn=fn.__name__):
				with as_user(CAPTAIN):
					with self.assertRaises(frappe.PermissionError):
						fn(branch=BRANCH)
				with as_user(CASHIER):  # the cache is really in use: the cashier gets the sentinel
					self.assertEqual(fn(branch=BRANCH), {"sentinel": 1})

	def test_every_function_checks_before_anything_else(self):
		"""A function added later without the check fails here (first statement after the docstring)."""
		self._assert_first_call(ury_dashboard, "require_sales_view")
		self._assert_first_call(ury_service_line, "require_sales_view")

	def _assert_first_call(self, module, check_name):
		tree = ast.parse(inspect.getsource(module))
		found = 0
		for node in tree.body:
			if not isinstance(node, ast.FunctionDef):
				continue
			if not any("whitelist" in ast.dump(d) for d in node.decorator_list):
				continue
			found += 1
			body = [
				stmt
				for stmt in node.body
				if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant))
			]
			first = body[0]
			ok = (
				isinstance(first, ast.Expr)
				and isinstance(first.value, ast.Call)
				and getattr(first.value.func, "id", None) == check_name
			)
			self.assertTrue(ok, f"{module.__name__}.{node.name} must start with {check_name}()")
		self.assertTrue(found, f"no whitelisted function found in {module.__name__}")

	def test_the_pos_tells_the_screen_who_sees_the_dashboard(self):
		answers = {}
		for user in (CAPTAIN, CASHIER, MANAGER):
			with as_user(user):
				answers[user] = get_pos_permissions().get("view_dashboard")
		self.assertEqual(answers, {CAPTAIN: False, CASHIER: True, MANAGER: True})


class TestReportGate(DashboardCase):
	"""Level B: the reports and the admin app."""

	def test_cashier_and_captain_are_refused(self):
		for user in (CAPTAIN, CASHIER):
			with self.subTest(user=user), as_user(user):
				with self.assertRaises(frappe.PermissionError):
					require_manager()

	def test_manager_admin_and_system_manager_pass(self):
		for user in (MANAGER, ADMIN, SYSTEM_MANAGER, "Administrator"):
			with self.subTest(user=user), as_user(user):
				require_manager()

	def test_real_endpoints_follow(self):
		for user in (CAPTAIN, CASHIER):
			with as_user(user):
				with self.assertRaises(frappe.PermissionError):
					sales.get_today_sales(branch=BRANCH)
				with self.assertRaises(frappe.PermissionError):
					customers.search_customers("a")
		for user in (MANAGER, ADMIN):
			with as_user(user):
				sales.get_today_sales(branch=BRANCH)

	def test_the_decision_is_the_doctype_permission_not_a_role_name(self):
		"""A role nobody named in the code passes when it may read URY Report Settings, and stops passing
		when that permission is taken away."""
		role = "Dash Test Viewer"
		email = "dash-viewer@test.local"
		self.addCleanup(lambda: frappe.delete_doc("User", email, force=True, ignore_permissions=True) if frappe.db.exists("User", email) else None)
		self.addCleanup(lambda: frappe.delete_doc("Role", role, force=True, ignore_permissions=True) if frappe.db.exists("Role", role) else None)
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role}).insert(ignore_permissions=True)
		make_user(email, role)

		with as_user(email):
			with self.assertRaises(frappe.PermissionError):
				require_manager()

		perm = frappe.get_doc(
			{"doctype": "Custom DocPerm", "parent": "URY Report Settings", "parenttype": "DocType",
			 "parentfield": "permissions", "role": role, "permlevel": 0, "read": 1}
		).insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("Custom DocPerm", perm.name, force=True, ignore_permissions=True) if frappe.db.exists("Custom DocPerm", perm.name) else None)
		frappe.clear_cache()
		with as_user(email):
			require_manager()

	def test_every_whitelisted_report_function_starts_with_the_check(self):
		count = 0
		for name in ("customers", "employees", "financial", "items", "operations", "sales"):
			module = importlib.import_module(f"ury.ury.report_api.{name}")
			tree = ast.parse(inspect.getsource(module))
			for node in tree.body:
				if not (isinstance(node, ast.FunctionDef) and any("whitelist" in ast.dump(d) for d in node.decorator_list)):
					continue
				count += 1
				body = [s for s in node.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
				first = body[0]
				self.assertTrue(
					isinstance(first, ast.Expr) and isinstance(first.value, ast.Call)
					and getattr(first.value.func, "id", None) == "require_manager",
					f"report_api.{name}.{node.name} must start with require_manager()",
				)
		self.assertGreaterEqual(count, 20)


class TestAdminAppData(DashboardCase):
	"""get_recent_transactions and get_module_records: managers only, nine DocTypes, the fields the pages show."""

	def test_what_the_user_page_may_do(self):
		# the page asks which buttons to show: create and write on the User DocType, for the logged-in user
		for user, expected in ((SYSTEM_MANAGER, {"create": True, "write": True}), (MANAGER, {"create": False, "write": False})):
			with as_user(user):
				self.assertEqual(dashboard.get_module_permissions("User"), expected, user)
		for user in (ADMIN, "Administrator"):
			with as_user(user):
				granted = frappe.permissions.get_role_permissions(frappe.get_meta("User"))
				self.assertEqual(
					dashboard.get_module_permissions("User"),
					{"create": bool(granted.get("create")), "write": bool(granted.get("write"))},
					user,
				)

	def test_a_user_shared_one_document_does_not_get_the_edit_button(self):
		# Frappe shares every User with the user themselves, and has_permission("User", "write") is then true for all
		self.assertTrue(frappe.get_all("DocShare", filters={"share_doctype": "User", "user": MANAGER, "write": 1}))
		with as_user(MANAGER):
			self.assertTrue(frappe.has_permission("User", "write"))  # the trap
			self.assertFalse(dashboard.get_module_permissions("User")["write"])

	def test_what_the_user_page_may_do_is_for_managers_and_the_nine_doctypes_only(self):
		for user in (CAPTAIN, CASHIER):
			with as_user(user), self.assertRaises(frappe.PermissionError):
				dashboard.get_module_permissions("User")
		with as_user(MANAGER), self.assertRaises(frappe.PermissionError):
			dashboard.get_module_permissions("POS Invoice")

	ALLOWED = {"Branch", "URY Room", "URY Table", "URY Production Unit", "URY Menu", "URY Menu Course", "Item Group", "Item", "User"}
	USER_KEYS = {"name", "email", "first_name", "last_name", "full_name", "user_type", "enabled", "roles"}

	def test_captain_and_cashier_are_refused(self):
		for user in (CAPTAIN, CASHIER):
			with as_user(user):
				with self.assertRaises(frappe.PermissionError):
					dashboard.get_recent_transactions(branch=BRANCH)
				for doctype in ("Branch", "User"):
					with self.assertRaises(frappe.PermissionError):
						dashboard.get_module_records(doctype, "all")
				with self.assertRaises(frappe.PermissionError):
					dashboard.get_dashboard_summary()
				with self.assertRaises(frappe.PermissionError):
					dashboard.get_dashboard_charts()

	def test_other_doctypes_are_refused_even_for_a_manager(self):
		for doctype in ("Customer", "Salary Slip", "DocType", "Has Role", "Sales Invoice", "POS Invoice", "Role", "Email Account"):
			for user in (MANAGER, ADMIN, "Administrator"):
				with self.subTest(doctype=doctype, user=user), as_user(user):
					with self.assertRaises(frappe.PermissionError):
						dashboard.get_module_records(doctype, "all")

	def test_the_nine_doctypes_work_for_a_manager(self):
		for doctype in sorted(self.ALLOWED):
			with self.subTest(doctype=doctype), as_user(MANAGER):
				self.assertIsInstance(dashboard.get_module_records(doctype, "all"), list)

	def test_a_manager_sees_the_other_users_on_the_user_page(self):
		with as_user(MANAGER):
			records = dashboard.get_module_records("User", "all")
		names = {row["name"] for row in records}
		self.assertIn(CAPTAIN, names)
		self.assertIn(CASHIER, names)
		captain = next(row for row in records if row["name"] == CAPTAIN)
		self.assertIn("URY Captain", [r["role"] for r in captain["roles"]])

	def test_user_records_carry_no_secret(self):
		make_user(SENSITIVE, "URY Cashier")
		frappe.db.set_value(
			"User", SENSITIVE,
			{"api_key": "test-api-key-123", "reset_password_key": "test-reset-key-456", "last_ip": "10.1.2.3", "phone": "03-0000-0000"},
		)
		for user in (MANAGER, ADMIN):
			with as_user(user):
				records = dashboard.get_module_records("User", "all")
			row = next(r for r in records if r["name"] == SENSITIVE)
			self.assertLessEqual(set(row), self.USER_KEYS, f"{user} got more than the user page needs")
			self.assertNotIn("test-api-key-123", repr(records))
			self.assertNotIn("test-reset-key-456", repr(records))

	def test_branch_filter_still_works(self):
		with as_user(MANAGER):
			rows = dashboard.get_module_records("URY Table", BRANCH)
		self.assertTrue(rows)
		self.assertEqual({row.get("branch") for row in rows}, {BRANCH})

	def test_recent_transactions_for_a_manager(self):
		for user in (MANAGER, ADMIN):
			with as_user(user):
				self.assertIsInstance(dashboard.get_recent_transactions(branch=BRANCH), list)

	def test_the_old_copy_of_the_module_is_gone(self):
		with self.assertRaises(ModuleNotFoundError):
			importlib.import_module("ury.api.dashboard")

	def test_every_function_of_the_module_starts_with_the_check(self):
		tree = ast.parse(inspect.getsource(dashboard))
		count = 0
		for node in tree.body:
			if not (isinstance(node, ast.FunctionDef) and any("whitelist" in ast.dump(d) for d in node.decorator_list)):
				continue
			count += 1
			body = [s for s in node.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
			first = body[0]
			self.assertTrue(
				isinstance(first, ast.Expr) and isinstance(first.value, ast.Call)
				and getattr(first.value.func, "id", None) == "require_manager",
				f"dashboard.{node.name} must start with require_manager()",
			)
		self.assertEqual(count, 5)  # summary, charts, recent transactions, module records, module permissions


STAFF_ROLES = ("URY Captain", "URY Cashier")


def effective_export_rows(role):
	"""[(doctype, permlevel)] where `role` has export. Frappe reads the Custom DocPerm rows of a DocType when it
	has any (for any role), otherwise the standard DocPerm rows."""
	custom_doctypes = set(frappe.get_all("Custom DocPerm", pluck="parent", distinct=True))
	rows = frappe.get_all("Custom DocPerm", filters={"role": role, "export": 1}, fields=["parent", "permlevel"])
	rows += [
		r
		for r in frappe.get_all("DocPerm", filters={"role": role, "export": 1}, fields=["parent", "permlevel"])
		if r.parent not in custom_doctypes
	]
	return sorted((r.parent, r.permlevel) for r in rows)


class TestStaffExport(DashboardCase):
	"""The captain and the cashier cannot export anything (a whole list as a file, customers and users included);
	the manager and the admin can export POS Invoices."""

	def test_guard_no_doctype_gives_staff_export(self):
		# every DocType on the site: a new DocType whose permission rows forget "export": 0 fails here
		for role in STAFF_ROLES:
			self.assertEqual(effective_export_rows(role), [], role)

	def test_pos_invoice_in_particular(self):
		for user in (CAPTAIN, CASHIER):
			self.assertFalse(frappe.has_permission("POS Invoice", "export", user=user), user)

	def test_manager_and_admin_keep_pos_invoice_export(self):
		for role in ("URY Manager", "URY Admin"):
			self.assertEqual(
				frappe.db.get_value("Custom DocPerm", {"parent": "POS Invoice", "role": role, "permlevel": 0}, "export"), 1
			)

	def test_the_rest_of_their_rights_are_untouched(self):
		for user, wants in ((CAPTAIN, ("read", "write", "create", "print")), (CASHIER, ("read", "write", "create", "submit", "cancel", "print"))):
			for ptype in wants:
				self.assertTrue(frappe.has_permission("POS Invoice", ptype, user=user), f"{user} {ptype}")
		self.assertTrue(frappe.has_permission("Customer", "read", user=CASHIER))
		self.assertTrue(frappe.has_permission("URY KOT", "read", user=CAPTAIN))

	def test_new_sites_get_an_explicit_zero_on_every_entry(self):
		from ury.role_permissions import permissions_map

		for role in STAFF_ROLES:
			self.assertTrue(permissions_map[role])
			for doctype, perms in permissions_map[role]:
				self.assertIn("export", perms, f"{role} {doctype}: write \"export\": 0, do not rely on the default")
				self.assertEqual(perms["export"], 0, f"{role} {doctype}")

	def test_the_doctype_files_do_not_give_export_either(self):
		import json
		import os

		import ury

		root = os.path.join(os.path.dirname(ury.__file__), "ury", "doctype")
		checked = 0
		for folder in sorted(os.listdir(root)):
			path = os.path.join(root, folder, folder + ".json")
			if not os.path.exists(path):
				continue
			with open(path, encoding="utf-8") as handle:
				for row in json.load(handle).get("permissions", []):
					if row.get("role") in STAFF_ROLES:
						checked += 1
						self.assertEqual(row.get("export", 0), 0, f"{folder} {row['role']}")
		self.assertGreater(checked, 5)

	def test_the_patch_takes_it_away_and_can_run_twice(self):
		from ury.patches.v3_0.revoke_staff_export import execute

		rows = {}
		for table in ("Custom DocPerm", "DocPerm"):
			for r in frappe.get_all(table, filters={"role": ("in", STAFF_ROLES)}, fields=["name", "export"]):
				rows[(table, r.name)] = r.export
		manager = {
			(t, r.name): r.export
			for t in ("Custom DocPerm", "DocPerm")
			for r in frappe.get_all(t, filters={"role": ("in", ("URY Manager", "URY Admin"))}, fields=["name", "export"])
		}

		def restore():
			for (table, name), value in rows.items():
				frappe.db.set_value(table, name, "export", value, update_modified=False)
			frappe.clear_cache()

		self.addCleanup(restore)  # (the patch does not commit; this keeps the test site as it was in any case)
		for table, name in rows:
			frappe.db.set_value(table, name, "export", 1, update_modified=False)
		frappe.clear_cache()
		self.assertTrue(effective_export_rows("URY Captain"))  # the starting point is really "has it"
		execute()
		execute()
		for role in STAFF_ROLES:
			self.assertEqual(effective_export_rows(role), [], role)
		for (table, name), value in manager.items():
			self.assertEqual(frappe.db.get_value(table, name, "export"), value, f"{table} {name}")
