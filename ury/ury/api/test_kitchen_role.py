"""The role URY Kitchen (2026-11-14): the account of a kitchen screen (/mosaic). It sees the tickets of its branch, serves
them and confirms the cancel tickets; it takes no order, takes no payment, cancels nothing, exports nothing, and has no Desk.
Run on the test site only (a trial site first: it creates a user and a Branch row)."""

from unittest import mock

import frappe

from ury.setup.test_site import (
	BRANCH,
	CAPTAIN,
	CASHIER,
	FOOD_ITEM,
	PRODUCTION_UNIT,
	URYFlowTestCase,
	as_user,
	open_pos,
	place_order,
)
from ury.ury.api import ury_kot_display

KITCHEN = "kitchen-role@test.local"
ROLE = "URY Kitchen"


def _remove_kitchen_user():
	frappe.db.delete("URY User", {"parenttype": "Branch", "user": KITCHEN})
	if frappe.db.exists("User", KITCHEN):
		frappe.delete_doc("User", KITCHEN, force=True, ignore_permissions=True)
	frappe.db.commit()


def effective_export_rows(role):
	custom_doctypes = set(frappe.get_all("Custom DocPerm", pluck="parent", distinct=True))
	rows = frappe.get_all("Custom DocPerm", filters={"role": role, "export": 1}, fields=["parent", "permlevel"])
	rows += [
		r
		for r in frappe.get_all("DocPerm", filters={"role": role, "export": 1}, fields=["parent", "permlevel"])
		if r.parent not in custom_doctypes
	]
	return sorted((r.parent, r.permlevel) for r in rows)


class TestKitchenRole(URYFlowTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.addClassCleanup(_remove_kitchen_user)
		_remove_kitchen_user()
		frappe.get_doc(
			{"doctype": "User", "email": KITCHEN, "first_name": "Kitchen", "send_welcome_email": 0, "enabled": 1,
			 "roles": [{"role": ROLE}]}
		).insert(ignore_permissions=True)
		branch = frappe.get_doc("Branch", BRANCH)
		branch.append("user", {"user": KITCHEN})
		branch.save(ignore_permissions=True)
		frappe.db.commit()
		frappe.clear_cache(user=KITCHEN)

	def setUp(self):
		super().setUp()
		open_pos(CASHIER)

	def _a_ticket(self):
		invoice = place_order(CASHIER, [(FOOD_ITEM, 1)], order_type="Take Away")
		return frappe.get_all("URY KOT", filters={"invoice": invoice, "production": PRODUCTION_UNIT}, pluck="name")[0]

	# --- the role --------------------------------------------------------------------------------------------------
	def test_the_role_is_for_the_kitchen_screen_and_has_no_desk(self):
		role = frappe.db.get_value("Role", ROLE, ["desk_access", "home_page"], as_dict=True)
		self.assertIsNotNone(role, "the role URY Kitchen does not exist")
		self.assertEqual(role.desk_access, 0)
		self.assertEqual(role.home_page, "mosaic")

	def test_an_account_with_only_this_role_is_a_website_user(self):
		self.assertEqual(frappe.db.get_value("User", KITCHEN, "user_type"), "Website User")

	# --- what the kitchen screen does ------------------------------------------------------------------------------------
	def test_it_sees_the_tickets_of_its_branch_and_the_kitchens(self):
		ticket = self._a_ticket()
		with as_user(KITCHEN):
			seen = [row["name"] for row in ury_kot_display.kot_list()["KOT"]]
			self.assertIn(ticket, seen)
			units = frappe.get_list("URY Production Unit", fields=["name"], pluck="name")
			self.assertIn(PRODUCTION_UNIT, units)
			self.assertGreaterEqual(frappe.get_list("URY KOT", fields=["count(name) as n"])[0]["n"], 1)

	def test_it_serves_a_ticket(self):
		ticket = self._a_ticket()
		with as_user(KITCHEN):
			ury_kot_display.serve_kot(ticket)
		self.assertEqual(frappe.db.get_value("URY KOT", ticket, "order_status"), "Served")

	def test_it_confirms_a_cancel_ticket_of_its_branch(self):
		ticket = self._a_ticket()
		frappe.db.set_value("URY KOT", ticket, "type", "Cancelled")
		with as_user(KITCHEN):
			ury_kot_display.confirm_cancel_kot(ticket)
		self.assertEqual(frappe.db.get_value("URY KOT", ticket, ["verified", "verified_by"]), (1, KITCHEN))

	def test_it_does_not_confirm_a_cancel_ticket_of_another_branch(self):
		ticket = self._a_ticket()
		frappe.db.set_value("URY KOT", ticket, "type", "Cancelled")
		with as_user(KITCHEN), mock.patch.object(ury_kot_display, "getBranch", return_value="Another branch"):
			with self.assertRaises(frappe.PermissionError):
				ury_kot_display.confirm_cancel_kot(ticket)
		self.assertEqual(frappe.db.get_value("URY KOT", ticket, "verified"), 0)

	def test_the_waiter_still_does_not_confirm_a_cancel_ticket(self):
		ticket = self._a_ticket()
		frappe.db.set_value("URY KOT", ticket, "type", "Cancelled")
		with as_user(CAPTAIN):
			with self.assertRaises(frappe.PermissionError):
				ury_kot_display.confirm_cancel_kot(ticket)

	def test_it_reads_the_name_of_its_own_user_for_the_header(self):
		with as_user(KITCHEN):
			self.assertEqual(frappe.get_value("User", KITCHEN, "full_name"), "Kitchen")
			self.assertEqual(frappe.session.user, KITCHEN)

	def test_the_branch_kitchens_for_the_redirect_are_given_to_the_account(self):
		from ury.ury_pos.api import get_production_units_for_branch

		with as_user(KITCHEN):
			self.assertIn(PRODUCTION_UNIT, get_production_units_for_branch()["production_units"])

	# --- what it does not do ------------------------------------------------------------------------------------------
	def test_it_takes_no_order_no_payment_and_cancels_nothing(self):
		invoice = place_order(CASHIER, [(FOOD_ITEM, 1)], order_type="Take Away")
		with as_user(KITCHEN):
			for doctype in ("POS Invoice", "Sales Invoice", "POS Closing Entry", "POS Opening Entry", "Payment Entry"):
				for ptype in ("write", "create", "submit", "cancel", "delete"):
					self.assertFalse(frappe.has_permission(doctype, ptype), f"{doctype} {ptype}")
			self.assertFalse(frappe.has_permission("POS Invoice", "write", doc=invoice))
			self.assertFalse(frappe.has_permission("POS Invoice", "read", doc=invoice))

	def test_it_cannot_change_the_roles_of_its_account_or_read_the_other_users(self):
		with as_user(KITCHEN):
			self.assertFalse(frappe.has_permission("User", "create"))
			self.assertFalse(frappe.has_permission("User", "read", doc=CASHIER))

	def test_it_exports_nothing(self):
		self.assertEqual(effective_export_rows(ROLE), [])

	def test_it_cannot_create_or_delete_a_ticket(self):
		with as_user(KITCHEN):
			self.assertFalse(frappe.has_permission("URY KOT", "create"))
			self.assertFalse(frappe.has_permission("URY KOT", "delete"))
			self.assertFalse(frappe.has_permission("URY Production Unit", "write"))


class TestKitchenAccountFromTheWizard(URYFlowTestCase):
	def test_the_wizard_may_make_a_kitchen_account_but_still_not_a_system_manager(self):
		from ury.ury.api.minimal.business_setup import check_staff_role

		check_staff_role("URY Kitchen")  # no error
		with self.assertRaises(frappe.ValidationError):
			check_staff_role("System Manager")
