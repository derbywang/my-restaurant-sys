"""Who may use the setup endpoints and the table merging endpoints.

`create_setup_user`, `update_business_setup` and `submit_configure_data` work with `ignore_permissions`; they used to
check only that the caller was not a guest, so any logged-in user (a waiter) could make an account with any role,
System Manager included. Now only an administrator (System Manager, URY Admin) may call them, and an account made
through them gets one of the staff roles. Merging and unmerging tables is for the staff of the table's branch.
Run on the test site only.
"""

import frappe

from ury.setup.test_site import CAPTAIN, CASHIER, MANAGER, TABLES, URYFlowTestCase, as_user
from ury.ury.api.minimal.business_setup import create_setup_user, submit_configure_data, update_business_setup
from ury.ury.doctype.ury_order.ury_order import merge_tables_batch, unmerge_tables

SITE_ADMIN = "admin@test.local"  # has System Manager (and every URY role)
NEW = "new-staff@test.local"
ONLY_URY_ADMIN = "only-ury-admin@test.local"
STRANGER = "stranger@test.local"  # no role at all
OTHER_BRANCH_STAFF = "other-branch-staff@test.local"
OTHER_BRANCH = "別の店（権限テスト）"
REFUSED = (frappe.PermissionError, frappe.ValidationError)


def make_user(email, roles=()):
	frappe.delete_doc("User", email, force=True, ignore_permissions=True)
	frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": "Test",
			"send_welcome_email": 0,
			"user_type": "System User",
			"roles": [{"role": role} for role in roles],
		}
	).insert(ignore_permissions=True)
	frappe.db.commit()


def roles_of(email):
	return set(frappe.get_all("Has Role", filters={"parent": email, "parenttype": "User"}, pluck="role"))


class SetupCase(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(self._clean)
		self._clean()

	def _clean(self):
		for email in (NEW, ONLY_URY_ADMIN, STRANGER, OTHER_BRANCH_STAFF):
			frappe.delete_doc("User", email, force=True, ignore_permissions=True) if frappe.db.exists("User", email) else None
		frappe.db.commit()

	def made(self):
		return frappe.db.exists("User", NEW)


class TestCreateSetupUser(SetupCase):
	def test_a_waiter_or_a_cashier_cannot_make_an_account(self):
		for user in (CAPTAIN, CASHIER, MANAGER):
			with as_user(user), self.assertRaises(frappe.PermissionError):
				create_setup_user(NEW, "Someone", "A-long-pass-123", "URY Cashier")
			self.assertFalse(self.made(), user)

	def test_nobody_can_make_a_system_manager_or_any_other_role(self):
		for user in (CAPTAIN, MANAGER, SITE_ADMIN, "Administrator"):
			for role in ("System Manager", "Administrator", "URY Admin", "Desk User", ""):
				with as_user(user), self.assertRaises(REFUSED):
					create_setup_user(NEW, "Someone", "A-long-pass-123", role)
				self.assertFalse(self.made(), (user, role))

	def test_an_administrator_makes_an_account_with_the_one_role(self):
		for role in ("URY Cashier", "URY Captain", "URY Manager"):
			with as_user(SITE_ADMIN):
				self.assertEqual(create_setup_user(NEW, "Someone", "A-long-pass-123", role)["status"], "created")
			self.assertEqual(roles_of(NEW), {role})
			frappe.delete_doc("User", NEW, force=True, ignore_permissions=True)
			frappe.db.commit()

	def test_the_ury_admin_role_is_enough_for_every_staff_role(self):
		make_user(ONLY_URY_ADMIN, ["URY Admin"])
		for role in ("URY Cashier", "URY Captain", "URY Manager"):
			with as_user(ONLY_URY_ADMIN):
				self.assertEqual(create_setup_user(NEW, "Someone", None, role)["status"], "created")
			self.assertEqual(roles_of(NEW), {role})
			frappe.delete_doc("User", NEW, force=True, ignore_permissions=True)
			frappe.db.commit()

	def test_an_existing_account_is_left_alone(self):
		before = roles_of(MANAGER)
		with as_user(SITE_ADMIN):
			self.assertEqual(create_setup_user(MANAGER, "Someone", "A-long-pass-123", "URY Cashier")["status"], "exists")
		self.assertEqual(roles_of(MANAGER), before)

	def test_a_waiter_is_not_told_whether_an_account_exists(self):
		for email in (MANAGER, NEW):
			with as_user(CAPTAIN), self.assertRaises(frappe.PermissionError):
				create_setup_user(email, "Someone", None, "URY Cashier")


class TestTheOtherSetupEndpoints(SetupCase):
	def test_a_waiter_or_a_cashier_cannot_run_the_configuration(self):
		data = {"users": [{"email": NEW, "name": "Someone", "role": "URY Cashier"}]}
		for user in (CAPTAIN, CASHIER, MANAGER):
			with as_user(user), self.assertRaises(frappe.PermissionError):
				submit_configure_data(data)
			self.assertFalse(self.made(), user)

	def test_a_wrong_role_in_the_configuration_refuses_it_whole(self):
		data = {
			"users": [
				{"email": NEW, "name": "Someone", "role": "URY Cashier"},
				{"email": "other-new@test.local", "name": "Other", "role": "System Manager"},
			]
		}
		with as_user(SITE_ADMIN), self.assertRaises(REFUSED):
			submit_configure_data(data)
		self.assertFalse(self.made())
		self.assertFalse(frappe.db.exists("User", "other-new@test.local"))

	def test_a_waiter_or_a_cashier_cannot_change_the_business_setup(self):
		for user in (CAPTAIN, CASHIER, MANAGER):
			with as_user(user), self.assertRaises(frappe.PermissionError):
				update_business_setup(branch={"name": "テスト店", "branch": "改名された店"})
		self.assertEqual(frappe.db.get_value("Branch", "テスト店", "branch"), "テスト店")


class TestMergingTables(SetupCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(self._unmerge)

	def _unmerge(self):
		frappe.db.set_value("URY Table", {"name": ["in", list(TABLES)]}, "merged_with", None)
		frappe.db.delete("Branch", {"name": OTHER_BRANCH})
		frappe.db.commit()

	def merged_with(self):
		return {name: frappe.db.get_value("URY Table", name, "merged_with") for name in TABLES}

	def test_someone_without_a_role_cannot_merge_or_unmerge(self):
		make_user(STRANGER)
		before = self.merged_with()
		with as_user(STRANGER):
			with self.assertRaises(frappe.PermissionError):
				merge_tables_batch(TABLES[0], [TABLES[1]])
		self.assertEqual(self.merged_with(), before)
		with as_user(CAPTAIN):
			merge_tables_batch(TABLES[0], [TABLES[1]])
		merged = self.merged_with()
		with as_user(STRANGER), self.assertRaises(frappe.PermissionError):
			unmerge_tables(TABLES[0])
		self.assertEqual(self.merged_with(), merged)

	def test_the_staff_of_another_branch_cannot(self):
		make_user(OTHER_BRANCH_STAFF, ["URY Captain"])
		frappe.get_doc({"doctype": "Branch", "branch": OTHER_BRANCH, "user": [{"user": OTHER_BRANCH_STAFF}]}).insert(
			ignore_permissions=True
		)
		frappe.db.commit()
		before = self.merged_with()
		with as_user(OTHER_BRANCH_STAFF), self.assertRaises(frappe.PermissionError):
			merge_tables_batch(TABLES[0], [TABLES[1]])
		self.assertEqual(self.merged_with(), before)

	def test_a_waiter_still_merges_and_unmerges_the_tables_of_the_branch(self):
		with as_user(CAPTAIN):
			merge_tables_batch(TABLES[0], [TABLES[1]])
		merged = self.merged_with()
		self.assertTrue(merged[TABLES[0]] and merged[TABLES[1]])
		with as_user(CAPTAIN):
			unmerge_tables(TABLES[0])
		self.assertEqual(self.merged_with(), {name: None for name in TABLES})
