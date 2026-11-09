"""A discount on the whole order, by tax rate (税理士, 2026-11-09): the discount and the amount after it can be read for each
rate on the receipt and in the payment dialog's totals. Run on the test site only."""

import frappe
from frappe.utils import add_to_date

from ury.setup.jp_tax import refresh_receipt_format
from ury.setup.test_site import (
	ALCOHOL_ITEM,
	CASHIER,
	FOOD_ITEM,
	POS_PROFILE,
	TABLES,
	URYFlowTestCase,
	as_user,
	open_pos,
	place_order,
)
from ury.ury.api.order_totals import preview_order_totals
from ury.ury.api.test_receipt import render, text
from ury.ury_pos.api import merge_bills


class TestDiscountByRate(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		profile = frappe.db.get_value("POS Profile", POS_PROFILE, ["apply_discount_on", "custom_enable_discount"])
		self.addCleanup(self._set_discount, *profile)
		self._set_discount("Net Total", 1)
		refresh_receipt_format()
		frappe.db.commit()
		open_pos(CASHIER)

	def _set_discount(self, apply_on, enabled):
		frappe.db.set_value("POS Profile", POS_PROFILE, {"apply_discount_on": apply_on, "custom_enable_discount": enabled})
		frappe.db.commit()
		frappe.clear_document_cache("POS Profile", POS_PROFILE)

	def _discounted(self, order, percentage):
		"""Save the order with the discount, the way the payment saves it (the receipt reads the saved amounts)."""
		doc = frappe.get_doc("POS Invoice", order)
		doc.additional_discount_percentage = percentage
		doc.save()
		frappe.db.commit()

	def test_one_rate_shows_the_amount_before_the_discount_the_discount_and_the_amount_after(self):
		order = place_order(CASHIER, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)], table=TABLES[0])
		self._discounted(order, 10)
		out = text(render(order))
		self.assertIn("10%対象 割引前（税抜） | ¥1,500", out)
		self.assertIn("割引 10%対象 | -¥150", out)
		self.assertIn("10%対象（税抜） | ¥1,350", out)
		self.assertIn("消費税等 10% | ¥135", out)

	def test_two_rates_each_have_their_own_discount(self):
		order = place_order(CASHIER, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)], table=TABLES[0], order_type="Take Away")
		self._discounted(order, 10)
		doc = frappe.get_doc("POS Invoice", order)
		per_rate = {}
		for item in doc.items:
			rate = 10 if item.item_code == ALCOHOL_ITEM else 8
			gross, net = per_rate.get(rate, (0, 0))
			per_rate[rate] = (gross + item.amount, net + item.net_amount)
		out = text(render(order))
		for rate, (gross, net) in per_rate.items():
			self.assertIn(f"{rate}%対象 割引前（税抜） | ¥{gross:,.0f}", out)
			self.assertIn(f"割引 {rate}%対象 | -¥{gross - net:,.0f}", out)
			self.assertIn(f"{rate}%対象（税抜） | ¥{net:,.0f}", out)

	def test_the_discounts_of_the_rates_add_up_to_the_discount(self):
		order = place_order(CASHIER, [(FOOD_ITEM, 3), (ALCOHOL_ITEM, 2)], table=TABLES[0], order_type="Take Away")
		with as_user(CASHIER):
			totals = preview_order_totals(order, 15)
		self.assertAlmostEqual(sum(t["discount_amount"] for t in totals["taxes"]), totals["discount_amount"], delta=1)
		for tax in totals["taxes"]:
			self.assertEqual(tax["gross_amount"] - tax["discount_amount"], tax["taxable_amount"])

	def test_the_preview_has_the_amounts_by_rate_for_the_payment_dialog(self):
		order = place_order(CASHIER, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)], table=TABLES[0])
		with as_user(CASHIER):
			totals = preview_order_totals(order, 10)
		self.assertEqual(
			[(t["rate"], t["gross_amount"], t["discount_amount"], t["taxable_amount"], t["tax_amount"]) for t in totals["taxes"]],
			[(10, 1500, 150, 1350, 135)],
		)

	def test_without_a_discount_there_are_no_extra_lines(self):
		order = place_order(CASHIER, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)], table=TABLES[0])
		out = text(render(order))
		self.assertNotIn("割引前", out)
		self.assertNotIn("対象 |", out.replace("10%対象（税抜）", ""))
		with as_user(CASHIER):
			totals = preview_order_totals(order)
		self.assertEqual([t["discount_amount"] for t in totals["taxes"]], [0])

	def test_a_merged_bill_has_the_discount_of_both_by_rate(self):
		first = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])
		second = place_order(CASHIER, [(ALCOHOL_ITEM, 1)], table=TABLES[1])
		made = frappe.db.get_value("POS Invoice", first, "creation")
		frappe.db.set_value("POS Invoice", second, "creation", add_to_date(made, seconds=1), update_modified=False)
		with as_user(CASHIER):
			merge_bills(first, second)
		self._discounted(first, 10)
		self._discounted(second, 10)
		out = text(render(first))
		self.assertIn("10%対象 割引前（税抜） | ¥1,500", out)
		self.assertIn("割引 10%対象 | -¥150", out)
		self.assertIn("10%対象（税抜） | ¥1,350", out)
