"""deploy_check: the checks are read-only and report what is wrong. Test site, inside a rolled-back transaction."""

import frappe

from ury.setup.test_site import BRANCH, URYTestCase
from ury.ury.api import deploy_check

NEW_STAFF = "dc-new-staff@test.local"


class TestStaffInABranch(URYTestCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(self._remove)
		self._remove()
		frappe.get_doc(
			{"doctype": "User", "email": NEW_STAFF, "first_name": "New", "send_welcome_email": 0, "enabled": 1,
			 "roles": [{"role": "URY Cashier"}]}
		).insert(ignore_permissions=True)

	def _remove(self):
		frappe.db.delete("URY User", {"parenttype": "Branch", "user": NEW_STAFF})
		if frappe.db.exists("User", NEW_STAFF):
			frappe.delete_doc("User", NEW_STAFF, force=True, ignore_permissions=True)

	def test_a_new_account_in_no_branch_fails_and_is_named(self):
		ok, detail = deploy_check.staff_in_a_branch()
		self.assertFalse(ok)
		self.assertIn(NEW_STAFF, detail)

	def test_it_passes_once_the_account_is_in_a_branch(self):
		branch = frappe.get_doc("Branch", BRANCH)
		branch.append("user", {"user": NEW_STAFF})
		branch.save(ignore_permissions=True)
		_ok, detail = deploy_check.staff_in_a_branch()
		self.assertNotIn(NEW_STAFF, detail)

	def test_a_disabled_account_is_not_asked_for(self):
		frappe.db.set_value("User", NEW_STAFF, "enabled", 0)
		_ok, detail = deploy_check.staff_in_a_branch()
		self.assertNotIn(NEW_STAFF, detail)

	def test_administrator_and_guest_are_not_staff(self):
		_ok, detail = deploy_check.staff_in_a_branch()
		self.assertNotIn("Administrator", detail)
		self.assertNotIn("Guest", detail)

	def test_run_lists_failed_checks_first_and_writes_nothing(self):
		before = frappe.db.count("URY User")
		results = deploy_check.run()
		self.assertEqual(frappe.db.count("URY User"), before)
		self.assertEqual([r["ok"] for r in results], sorted(r["ok"] for r in results))
