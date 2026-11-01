"""Splitting a bill (会計分割, `split_bill`) with the tax, receipt, shift and merged-bill code.

These tests describe what the code does now (docs/design/jp-tax-design.md, 待确认事项);
where the result is not what a cashier would expect, the test says so. Run on the test site only.
"""

import frappe

from ury.setup.jp_tax import refresh_receipt_format
from ury.setup.test_site import (
	ALCOHOL_ITEM,
	CASHIER,
	FOOD_ITEM,
	POS_PROFILE,
	TABLES,
	URYFlowTestCase,
	as_user,
	close_shift,
	open_pos,
	pay_order,
	place_order,
	print_bill,
)
from ury.ury.api.merged_bill import AmountChanged, unmerge_bills
from ury.ury.api.order_totals import preview_order_totals
from ury.ury.api.test_receipt import render, text
from ury.ury.doctype.ury_order.ury_order import cancel_order, split_bill
from ury.ury_pos.api import merge_bills


class TestSplitBill(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		original = frappe.db.get_value("POS Profile", POS_PROFILE, ["apply_discount_on", "custom_enable_discount"])
		self.addCleanup(self._set_discount, *original)
		self._set_discount("Net Total", 1)
		refresh_receipt_format()
		frappe.db.commit()
		self.opening = open_pos(CASHIER)

	def _set_discount(self, apply_on, enabled):
		frappe.db.set_value("POS Profile", POS_PROFILE, {"apply_discount_on": apply_on, "custom_enable_discount": enabled})
		frappe.db.commit()
		frappe.clear_document_cache("POS Profile", POS_PROFILE)

	def _bill(self, items, table=TABLES[0], order_type="Dine In", discount=None):
		"""A printed draft bill; `discount` is a percentage saved on it."""
		name = place_order(CASHIER, items, table=table, order_type=order_type)
		if discount:
			doc = frappe.get_doc("POS Invoice", name)
			doc.additional_discount_percentage = discount
			doc.save()
		print_bill(name)
		return name

	def _split(self, source, item_code, qty=1):
		"""Move `qty` of `item_code` to a new bill; returns the name of the new bill."""
		row = frappe.db.get_value("POS Invoice Item", {"parent": source, "item_code": item_code}, ["name"])
		with as_user(CASHIER):
			return split_bill(source, [{"name": row, "qty": qty}])["new_invoice"]

	def _values(self, name, *fields):
		return frappe.db.get_value("POS Invoice", name, list(fields), as_dict=True)

	def _total(self, name):
		with as_user(CASHIER):
			return preview_order_totals(name)

	# --- the amounts -----------------------------------------------------------------------

	def test_the_two_bills_add_up_to_the_original(self):
		source = self._bill([(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)])
		new = self._split(source, ALCOHOL_ITEM)
		self.assertEqual((self._total(source)["rounded_total"], self._total(new)["rounded_total"]), (1100, 550))
		self.assertEqual(self._values(new, "restaurant_table").restaurant_table, TABLES[0])
		self.assertEqual(self._values(new, "invoice_printed").invoice_printed, 0)

	def test_each_bill_rounds_its_own_tax_so_the_total_can_differ_by_a_yen(self):
		"""Two beers at 5% off on one bill: 950 net, 95 tax. One beer on each of two bills:
		475 net, 47.5 -> 47 tax each, 94 together. T4 rounds the tax of each rate once per
		bill, so splitting a discounted bill can change the tax by 1 yen (待确认事项)."""
		one = self._bill([(ALCOHOL_ITEM, 2)], table=TABLES[0], discount=5)
		two = [self._bill([(ALCOHOL_ITEM, 1)], table=table, discount=5) for table in TABLES[1:]]
		self.assertEqual(self._total(one)["total_taxes_and_charges"], 95)
		self.assertEqual([self._total(name)["total_taxes_and_charges"] for name in two], [47, 47])

	def test_the_new_bill_gets_the_discount_percentage_of_the_original(self):
		source = self._bill([(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)], discount=10)
		self.assertEqual(self._total(source)["rounded_total"], 1485)
		new = self._split(source, ALCOHOL_ITEM)
		for name in (source, new):
			self.assertEqual(self._values(name, "additional_discount_percentage").additional_discount_percentage, 10)
		self.assertEqual(self._total(source)["rounded_total"], 990)  # 1,000 - 10% = 900, +10%
		self.assertEqual(self._total(new)["rounded_total"], 495)  # 500 - 10% = 450, +10%
		self.assertEqual(self._total(source)["rounded_total"] + self._total(new)["rounded_total"], 1485)

	def test_splitting_a_discounted_bill_can_change_the_tax_by_a_yen(self):
		"""Two beers at 5% off: 950 net, 95 tax. Split into one beer each: 475 net, 47.5 -> 47 tax
		each, 94 together (T4 rounds the tax of each rate once per bill; 待确认事项)."""
		source = self._bill([(ALCOHOL_ITEM, 2)], discount=5)
		self.assertEqual(self._total(source)["total_taxes_and_charges"], 95)
		new = self._split(source, ALCOHOL_ITEM)
		self.assertEqual([self._total(name)["total_taxes_and_charges"] for name in (source, new)], [47, 47])

	def test_the_new_bill_is_taxed_like_the_original(self):
		source = self._bill([(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)])
		new = self._split(source, ALCOHOL_ITEM)
		saved = frappe.get_doc("POS Invoice", new)
		self.assertEqual((saved.tax_category, saved.rounded_total), ("店内飲食", 550))
		self.assertEqual([(t.rate, t.tax_amount) for t in saved.taxes if t.tax_amount], [(10, 50)])

	def test_take_away_keeps_its_own_tax_on_both_bills(self):
		source = self._bill([(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)], order_type="Take Away", table=TABLES[0])
		new = self._split(source, FOOD_ITEM)
		self.assertEqual(self._total(new)["taxes"][0]["rate"], 8)
		self.assertEqual(self._total(new)["rounded_total"], 1080)
		self.assertEqual(self._total(source)["taxes"][0]["rate"], 10)

	# --- paying, the shift, the receipt --------------------------------------------------------

	def test_each_bill_is_paid_on_its_own_and_the_shift_counts_both(self):
		source = self._bill([(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)])
		new = self._split(source, ALCOHOL_ITEM)
		print_bill(new)
		pay_order(source)
		pay_order(new)
		closing = close_shift(self.opening)
		self.assertEqual({row.pos_invoice for row in closing.pos_transactions}, {source, new})
		self.assertEqual(closing.grand_total, 1650)
		self.assertEqual(sum(p.expected_amount for p in closing.payment_reconciliation), 1650)

	def test_the_receipts_show_only_the_items_of_each_bill(self):
		source = self._bill([(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)])
		new = self._split(source, ALCOHOL_ITEM)
		self.assertIn("合計（税込） | ¥1,100", text(render(source)))
		self.assertNotIn(ALCOHOL_ITEM, text(render(source)))
		out = text(render(new))
		self.assertIn("合計（税込） | ¥550", out)
		self.assertIn(ALCOHOL_ITEM, out)
		self.assertNotIn("1 × ¥1,000", out)  # (the company has the name of the sushi item)

	def test_the_prefilled_payment_row_of_the_new_bill_does_not_break_paying(self):
		source = self._bill([(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)])
		new = self._split(source, ALCOHOL_ITEM)
		print_bill(new)
		from ury.ury.doctype.ury_order.ury_order import make_invoice

		with as_user(CASHIER):
			make_invoice(
				customer=self._values(new, "customer").customer,
				payments=[{"mode_of_payment": "Cash", "amount": 1000}],
				cashier=CASHIER,
				pos_profile=POS_PROFILE,
				owner=CASHIER,
				table=TABLES[0],
				invoice=new,
				expected_total=550,
			)
		values = self._values(new, "status", "paid_amount", "change_amount")
		self.assertEqual((values.status, values.paid_amount, values.change_amount), ("Paid", 1000, 450))

	def test_a_bill_split_on_another_terminal_is_not_paid_at_the_old_amount(self):
		from ury.ury.doctype.ury_order.ury_order import make_invoice

		source = self._bill([(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)])
		shown = self._total(source)["rounded_total"]  # 1,650
		self._split(source, ALCOHOL_ITEM)
		with as_user(CASHIER), self.assertRaises(AmountChanged):
			make_invoice(
				customer=self._values(source, "customer").customer,
				payments=[{"mode_of_payment": "Cash", "amount": shown}],
				cashier=CASHIER,
				pos_profile=POS_PROFILE,
				owner=CASHIER,
				table=TABLES[0],
				invoice=source,
				expected_total=shown,
			)
		self.assertEqual(self._values(source, "status").status, "Draft")

	def test_cancelling_one_bill_leaves_the_other(self):
		source = self._bill([(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)])
		new = self._split(source, ALCOHOL_ITEM)
		with as_user("manager@test.local"):
			cancel_order(new, "test")
		self.assertEqual(self._values(new, "docstatus").docstatus, 2)
		self.assertEqual(self._values(source, "docstatus").docstatus, 0)
		self.assertEqual(self._total(source)["rounded_total"], 1100)

	# --- with a merged bill ---------------------------------------------------------------------

	def test_a_split_bill_can_be_merged_with_another_and_paid(self):
		from ury.ury.doctype.ury_order.ury_order import make_invoice

		source = self._bill([(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)])
		new = self._split(source, ALCOHOL_ITEM)
		other = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[1])
		with as_user(CASHIER):
			result = merge_bills(source, other)
		self.assertEqual(result["status"], "success", result)
		self.assertEqual(self._total(source)["rounded_total"], 1100 + 1100)
		print_bill(other)
		with as_user(CASHIER):
			make_invoice(
				customer=self._values(source, "customer").customer,
				payments=[{"mode_of_payment": "Cash", "amount": 2200}],
				cashier=CASHIER,
				pos_profile=POS_PROFILE,
				owner=CASHIER,
				table=TABLES[0],
				invoice=source,
				expected_total=2200,
			)
		self.assertEqual((self._values(source, "status").status, self._values(other, "status").status), ("Paid", "Paid"))
		self.assertEqual(self._values(new, "status").status, "Draft")  # the split-off bill is a separate bill

	def test_splitting_a_merged_bill_keeps_the_other_bill_in_step(self):
		first = self._bill([(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)])
		second = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[1])
		with as_user(CASHIER):
			merge_bills(first, second)
		new = self._split(first, ALCOHOL_ITEM)
		# the pair is still two bills paid as one; what moved to the new bill is no longer in it
		self.assertEqual(self._values(first, "custom_merged_pos_invoice").custom_merged_pos_invoice, second)
		self.assertEqual(self._values(second, "custom_merged_total").custom_merged_total, 1100)
		self.assertEqual(self._total(first)["rounded_total"], 1100 + 1100)
		self.assertFalse(self._values(new, "custom_merged_pos_invoice").custom_merged_pos_invoice)

	def test_a_split_bill_can_be_unmerged(self):
		first = self._bill([(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)])
		second = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[1])
		with as_user(CASHIER):
			merge_bills(first, second)
		new = self._split(first, ALCOHOL_ITEM)
		with as_user(CASHIER):
			unmerge_bills(first)
		self.assertEqual((self._total(first)["rounded_total"], self._total(second)["rounded_total"], self._total(new)["rounded_total"]), (1100, 1100, 550))
