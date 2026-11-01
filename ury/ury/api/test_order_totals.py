import frappe

from ury.setup.test_site import (
	ABBR,
	ALCOHOL_ITEM,
	CASHIER,
	FOOD_ITEM,
	POS_PROFILE,
	TABLES,
	URYFlowTestCase,
	as_user,
	open_pos,
	pay_order,
	place_order,
)
from ury.ury.api.order_totals import preview_order_totals


class TestPreviewOrderTotals(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		original = frappe.db.get_value("POS Profile", POS_PROFILE, ["apply_discount_on", "custom_enable_discount"])
		self.addCleanup(self._set_discount_on, *original)
		self._set_discount_on("Net Total", 1)
		open_pos(CASHIER)

	def _set_discount_on(self, value, enabled):
		frappe.db.set_value("POS Profile", POS_PROFILE, {"apply_discount_on": value, "custom_enable_discount": enabled})
		frappe.db.commit()
		frappe.clear_document_cache("POS Profile", POS_PROFILE)

	def _preview(self, invoice, discount=None):
		with as_user(CASHIER):
			return preview_order_totals(invoice, discount)

	def test_dine_in(self):
		order = place_order(CASHIER, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)], table=TABLES[0])
		totals = self._preview(order)
		self.assertEqual((totals["total"], totals["net_total"], totals["grand_total"], totals["rounded_total"]), (1500, 1500, 1650, 1650))
		self.assertEqual(
			[(t["account_head"], t["rate"], t["taxable_amount"], t["tax_amount"]) for t in totals["taxes"]],
			[(f"CT 10% - {ABBR}", 10, 1500, 150)],
		)

	def test_take_away_mixes_the_rates(self):
		order = place_order(CASHIER, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)], table=TABLES[0], order_type="Take Away")
		totals = self._preview(order)
		self.assertEqual(
			[(t["rate"], t["taxable_amount"], t["tax_amount"]) for t in totals["taxes"]],
			[(10, 500, 50), (8, 1000, 80)],
		)
		self.assertEqual(totals["grand_total"], 1630)

	def test_a_discount_is_taken_off_before_tax(self):
		order = place_order(CASHIER, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)], table=TABLES[0])
		totals = self._preview(order, 10)
		self.assertEqual((totals["net_total"], totals["discount_amount"], totals["grand_total"]), (1350, 150, 1485))
		self.assertEqual([(t["taxable_amount"], t["tax_amount"]) for t in totals["taxes"]], [(1350, 135)])

	def test_the_preview_is_the_amount_the_payment_will_have(self):
		order = place_order(CASHIER, [(FOOD_ITEM, 3), (ALCOHOL_ITEM, 1)], table=TABLES[0], order_type="Take Away")
		expected = self._preview(order, 10)
		paid = pay_order(order, discount=10)
		self.assertEqual(paid.rounded_total, expected["rounded_total"])
		self.assertEqual(paid.net_total, expected["net_total"])
		self.assertEqual([t.tax_amount for t in paid.taxes if t.tax_amount], [t["tax_amount"] for t in expected["taxes"]])

	def test_nothing_is_saved(self):
		order = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])
		before = frappe.db.get_value("POS Invoice", order, ["grand_total", "additional_discount_percentage", "modified"])
		self._preview(order, 50)
		self.assertEqual(frappe.db.get_value("POS Invoice", order, ["grand_total", "additional_discount_percentage", "modified"]), before)

	def test_bad_input_is_refused(self):
		order = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])
		for bad in (-1, 101):
			with self.assertRaises(frappe.ValidationError):
				self._preview(order, bad)
		paid = pay_order(order)
		with self.assertRaises(frappe.ValidationError):
			self._preview(paid.name)
