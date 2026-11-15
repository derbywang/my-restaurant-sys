"""A waiter sees the orders that are open, not the sales (docs/design/report-permissions.md, "完整版").

The waiter has the POS Invoice permission to take orders. Through the general interfaces (`frappe.client.get_list`,
`get_count`, the report view) that also lets them add up the day's sales. So whoever may not settle a bill (no `submit`
on POS Invoice) sees only the invoices that are still open (docstatus 0) of their own branch; whoever may settle a bill
sees everything. The decision is the DocType permission, never a role name. Run on the test site only.
"""

import frappe

from ury.ury.api.test_captain_access import CAPTAIN_B, OTHER_BRANCH, make_captain, remove_captain
from ury.ury.doctype.ury_order.ury_order import get_order_invoice, get_table_order_context
from ury.setup.test_site import (
	CAPTAIN,
	CASHIER,
	FOOD_ITEM,
	MANAGER,
	TABLES,
	URYFlowTestCase,
	as_user,
	open_pos,
	pay_order,
	place_order,
)


def names(rows):
	return {row["name"] if isinstance(row, dict) else row.name for row in rows}


class TestInvoiceVisibility(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		remove_captain(CAPTAIN_B)
		open_pos(CASHIER)
		self.open = place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLES[0])
		self.paid = pay_order(place_order(CAPTAIN, [(FOOD_ITEM, 2)], table=TABLES[1]))
		if not isinstance(self.paid, str):
			self.paid = self.paid.name
		self.addCleanup(remove_captain, CAPTAIN_B)

	def get_list(self, user, **kwargs):
		with as_user(user):
			return frappe.get_list("POS Invoice", **kwargs)

	def test_a_waiter_lists_the_open_orders_but_not_the_paid_ones(self):
		found = names(self.get_list(CAPTAIN, fields=["name"], limit_page_length=0))
		self.assertIn(self.open, found)
		self.assertNotIn(self.paid, found)

	def test_a_waiter_cannot_add_up_the_sales_of_the_paid_invoices(self):
		with as_user(CAPTAIN):
			everything = frappe.get_list("POS Invoice", fields=["sum(grand_total) as total", "count(name) as n"], filters={"docstatus": 1})
		self.assertFalse(everything[0].total)
		self.assertEqual(everything[0].n, 0)
		with as_user(CAPTAIN):
			self.assertEqual(frappe.client.get_count("POS Invoice", filters={"docstatus": 1}), 0)

	def test_a_waiter_cannot_open_or_print_a_paid_invoice(self):
		with as_user(CAPTAIN):
			self.assertFalse(frappe.has_permission("POS Invoice", "read", doc=self.paid))
			self.assertFalse(frappe.has_permission("POS Invoice", "print", doc=self.paid))
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc("POS Invoice", self.paid).check_permission("read")
			with self.assertRaises(frappe.PermissionError):
				frappe.client.get("POS Invoice", self.paid)

	def test_a_waiter_still_works_with_the_open_order(self):
		with as_user(CAPTAIN):
			self.assertTrue(frappe.has_permission("POS Invoice", "read", doc=self.open))
			self.assertTrue(frappe.has_permission("POS Invoice", "write", doc=self.open))
		with as_user(CAPTAIN):
			opened = get_order_invoice(invoiceNo=self.open, order_type="Dine In")
		self.assertTrue(opened)
		with as_user(CAPTAIN):
			context = get_table_order_context(TABLES[0])
		self.assertTrue(context["permissions"]["view"])

	def test_a_waiter_of_another_branch_sees_no_open_order_of_this_one(self):
		make_captain(CAPTAIN_B, branch=OTHER_BRANCH)
		found = names(self.get_list(CAPTAIN_B, fields=["name"], limit_page_length=0))
		self.assertNotIn(self.open, found)
		with as_user(CAPTAIN_B):
			self.assertFalse(frappe.has_permission("POS Invoice", "read", doc=self.open))

	def test_a_waiter_of_the_same_branch_sees_the_open_order(self):
		make_captain(CAPTAIN_B)
		found = names(self.get_list(CAPTAIN_B, fields=["name"], limit_page_length=0))
		self.assertIn(self.open, found)

	def test_the_cashier_and_the_manager_see_all(self):
		for user in (CASHIER, MANAGER):
			found = names(self.get_list(user, fields=["name"], limit_page_length=0))
			self.assertIn(self.open, found, user)
			self.assertIn(self.paid, found, user)
			with as_user(user):
				self.assertTrue(frappe.has_permission("POS Invoice", "read", doc=self.paid), user)

	def test_the_administrator_sees_all(self):
		found = names(frappe.get_list("POS Invoice", fields=["name"], limit_page_length=0))
		self.assertIn(self.paid, found)

	def test_what_the_server_does_by_itself_is_not_limited(self):
		# the server's own queries (get_all, ignore_permissions) are not the waiter's reach
		found = names(frappe.get_all("POS Invoice", fields=["name"], limit_page_length=0))
		self.assertIn(self.paid, found)

	def test_the_decision_is_the_permission_not_the_role_name(self):
		from ury.ury.api.invoice_visibility import may_see_sales

		self.assertTrue(may_see_sales(CASHIER))
		self.assertTrue(may_see_sales(MANAGER))
		self.assertTrue(may_see_sales("Administrator"))
		self.assertFalse(may_see_sales(CAPTAIN))
