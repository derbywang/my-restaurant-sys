"""Smoke tests of the test-site helpers: they must drive the real flows end to end."""

import frappe

from ury.setup.test_site import (
	ABBR,
	ALCOHOL_ITEM,
	CASHIER,
	CASHIER2,
	FOOD_ITEM,
	POS_PROFILE,
	TABLES,
	URYFlowTestCase,
	close_shift,
	disable_multiple_cashier,
	enable_multiple_cashier,
	open_pos,
	pay_order,
	place_order,
	reset_transactions,
)


class TestTestSiteFlows(URYFlowTestCase):
	def test_dine_in_order_is_taxed_paid_and_consolidated_at_closing(self):
		opening = open_pos(CASHIER)
		self.assertEqual((opening.docstatus, opening.status), (1, "Open"))

		first = place_order(CASHIER, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)], table=TABLES[0])
		second = place_order(CASHIER, [(FOOD_ITEM, 2)], table=TABLES[1], order_type="Take Away")

		paid_first = pay_order(first)
		paid_second = pay_order(second)

		# J1 (dine in): 10% on 1,500; take away food is 8% on 2,000
		self.assertEqual((paid_first.docstatus, paid_first.grand_total), (1, 1650))
		self.assertEqual((paid_second.docstatus, paid_second.grand_total), (1, 2160))

		closing = close_shift(opening)
		self.assertEqual((closing.docstatus, closing.status), (1, "Submitted"))

		logs = frappe.get_all(
			"POS Invoice Merge Log", filters={"pos_closing_entry": closing.name}, fields=["name", "consolidated_invoice"]
		)
		self.assertEqual(len(logs), 1)
		sales_invoice = frappe.get_doc("Sales Invoice", logs[0].consolidated_invoice)
		self.assertEqual(sales_invoice.grand_total, 1650 + 2160)
		# the tax of each rate is the sum of the POS invoices' (own account per rate)
		taxes = {row.account_head: row.tax_amount for row in sales_invoice.taxes}
		self.assertEqual(taxes[f"CT 10% - {ABBR}"], 150)
		self.assertEqual(taxes[f"CT 8% - {ABBR}"], 160)

	def test_reset_transactions_empties_the_sales_documents(self):
		open_pos(CASHIER)
		place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[2])
		self.assertTrue(frappe.db.count("POS Invoice"))
		reset_transactions()
		self.assertEqual(frappe.db.count("POS Invoice"), 0)
		self.assertEqual(frappe.db.count("POS Opening Entry"), 0)
		# masters are untouched
		self.assertTrue(frappe.db.exists("POS Profile", POS_PROFILE))
		self.assertTrue(frappe.db.count("Sales Taxes and Charges", {"parenttype": "Sales Taxes and Charges Template"}))

	def test_multiple_cashier_mode_can_be_switched_on_and_off(self):
		try:
			profile = enable_multiple_cashier(main=CASHIER)
			self.assertEqual(profile.custom_enable_multiple_cashier, 1)
			mains = [row.user for row in profile.applicable_for_users if row.custom_main_cashier]
			self.assertEqual(mains, [CASHIER])
			self.assertIn(CASHIER2, [row.user for row in profile.applicable_for_users])
		finally:
			profile = disable_multiple_cashier()
		self.assertEqual(profile.custom_enable_multiple_cashier, 0)
		self.assertFalse(any(row.custom_main_cashier for row in profile.applicable_for_users))
