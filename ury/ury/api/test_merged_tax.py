"""Merged bills (会計合算): the tax of each rate is rounded ONCE for the whole merged bill.

The 税理士 (2026-11-09): two orders handed over as one 適格簡易請求書 must have the tax of each rate rounded once on the
merged taxable amount; adding up the tax rounded on each order is not right. The two POS Invoices stay (kitchen, tables,
unmerge, cancel do not change): the bill made first keeps its own rounded tax, the bill made later takes the difference
(`merged_bill.apply_pair_tax`). docs/design/jp-tax-design.md. Run on the test site only.
"""

import frappe
from frappe.utils import add_to_date

from ury.setup.jp_tax import refresh_receipt_format
from ury.setup.test_site import (
	CASHIER,
	FOOD_ITEM,
	POS_PROFILE,
	TABLES,
	URYFlowTestCase,
	as_user,
	close_shift,
	open_pos,
	place_order,
	print_bill,
)
from ury.ury.api.order_totals import preview_order_totals
from ury.ury.api.merged_bill import unmerge_bills
from ury.ury.api.test_receipt import render, text
from ury.ury_pos.api import merge_bills

PRICE = 1005  # 10% of it is 100.5: each bill alone cuts it to 100, the two together are 201


class TestMergedTaxIsRoundedOnce(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		original = frappe.db.get_value("Item Price", {"item_code": FOOD_ITEM, "selling": 1}, "price_list_rate")
		self.addCleanup(self._set_price, original)
		self._set_price(PRICE)
		profile = frappe.db.get_value("POS Profile", POS_PROFILE, ["apply_discount_on", "custom_enable_discount"])
		self.addCleanup(self._set_discount, *profile)
		self._set_discount("Net Total", 1)
		refresh_receipt_format()
		frappe.db.commit()
		self.opening = open_pos(CASHIER)
		self.first = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])
		self.second = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[1])
		# the dev container's clock can step back: the bill made first is made first
		made = frappe.db.get_value("POS Invoice", self.first, "creation")
		frappe.db.set_value("POS Invoice", self.second, "creation", add_to_date(made, seconds=1), update_modified=False)
		with as_user(CASHIER):
			merge_bills(self.first, self.second)

	def _set_price(self, price):
		frappe.db.sql("update `tabItem Price` set price_list_rate = %s where item_code = %s and selling = 1", (price, FOOD_ITEM))
		frappe.db.commit()

	def _set_discount(self, apply_on, enabled):
		frappe.db.set_value("POS Profile", POS_PROFILE, {"apply_discount_on": apply_on, "custom_enable_discount": enabled})
		frappe.db.commit()
		frappe.clear_document_cache("POS Profile", POS_PROFILE)

	def _preview(self, invoice, discount=None):
		with as_user(CASHIER):
			return preview_order_totals(invoice, discount)

	def _pay(self, invoice, amount, discount=None):
		from ury.ury.doctype.ury_order.ury_order import make_invoice

		doc = frappe.get_doc("POS Invoice", invoice)
		print_bill(invoice, CASHIER)
		profile = frappe.get_doc("POS Profile", POS_PROFILE)
		with as_user(CASHIER):
			make_invoice(
				customer=doc.customer,
				payments=[{"mode_of_payment": profile.payments[0].mode_of_payment, "amount": amount}],
				cashier=CASHIER,
				pos_profile=POS_PROFILE,
				owner=CASHIER,
				additionalDiscount=discount,
				table=doc.restaurant_table,
				invoice=invoice,
				expected_total=amount,
			)

	def _tax_and_total(self, name):
		row = frappe.db.get_value("POS Invoice", name, ["total_taxes_and_charges", "rounded_total"], as_dict=True)
		return row.total_taxes_and_charges, row.rounded_total

	# --- the amount the dialog shows --------------------------------------------------

	def test_the_preview_of_either_bill_has_the_tax_rounded_once(self):
		for invoice in (self.first, self.second):
			totals = self._preview(invoice)
			self.assertEqual(totals["net_total"], 2010)
			self.assertEqual([(t["rate"], t["taxable_amount"], t["tax_amount"]) for t in totals["taxes"]], [(10, 2010, 201)])
			self.assertEqual(totals["rounded_total"], 2211)

	def test_a_bill_that_is_not_merged_is_as_before(self):
		other = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[2])
		self.assertEqual(self._preview(other)["rounded_total"], 1105)

	def test_after_unmerging_each_bill_is_rounded_by_itself_again(self):
		with as_user(CASHIER):
			unmerge_bills(self.first)
		self.assertEqual(self._preview(self.first)["rounded_total"], 1105)
		self.assertEqual(self._preview(self.second)["rounded_total"], 1105)

	# --- paying ------------------------------------------------------------------

	def test_the_bill_made_first_keeps_its_tax_and_the_other_takes_the_difference(self):
		self._pay(self.first, 2211)
		self.assertEqual(self._tax_and_total(self.first), (100, 1105))
		self.assertEqual(self._tax_and_total(self.second), (101, 1106))

	def test_paying_the_other_bill_gives_the_same_result(self):
		self._pay(self.second, 2211)
		self.assertEqual(self._tax_and_total(self.first), (100, 1105))
		self.assertEqual(self._tax_and_total(self.second), (101, 1106))

	def test_both_are_paid_and_the_payments_add_up(self):
		self._pay(self.first, 2211)
		rows = [frappe.db.get_value("POS Invoice", n, ["status", "paid_amount"], as_dict=True) for n in (self.first, self.second)]
		self.assertEqual([r.status for r in rows], ["Paid", "Paid"])
		self.assertEqual(sum(r.paid_amount for r in rows), 2211)

	def test_the_amount_the_old_way_gives_is_refused_as_changed(self):
		from ury.ury.api.merged_bill import AmountChanged

		print_bill(self.first, CASHIER)
		with self.assertRaises(AmountChanged):
			self._pay(self.first, 2210)

	def test_the_shift_has_the_tax_of_the_merged_bill(self):
		self._pay(self.first, 2211)
		closing = close_shift(self.opening)
		self.assertEqual(sum(t.amount for t in closing.taxes), 201)
		self.assertEqual(closing.grand_total, 2211)

	# --- a discount ------------------------------------------------------------------

	def test_with_a_discount_the_tax_is_still_rounded_once_on_the_whole(self):
		totals = self._preview(self.first, 10)
		net = totals["net_total"]
		self.assertEqual(totals["taxes"][0]["tax_amount"], (net * 10) // 100)
		self._pay(self.first, totals["rounded_total"], discount=10)
		taxes = self._tax_and_total(self.first)[0] + self._tax_and_total(self.second)[0]
		self.assertEqual(taxes, (net * 10) // 100)

	# --- the receipt -----------------------------------------------------------------

	def test_the_receipt_of_either_unpaid_bill_shows_the_merged_tax_once(self):
		for invoice in (self.first, self.second):
			page = text(render(invoice))
			self.assertIn("¥201", page)
			self.assertIn("¥2,010", page)
			self.assertIn("¥2,211", page)
			self.assertNotIn("¥200", page)

	def test_printing_the_unpaid_merged_bills_logs_no_difference(self):
		"""The saved amounts of an unpaid merged pair are each bill's own (the pair is rounded once when it is paid):
		the receipt's self-check must not call that a difference (it did: an Error Log for every print)."""
		before = frappe.db.count("Error Log", {"method": ["like", "Receipt:%"]})
		for invoice in (self.first, self.second):
			text(render(invoice))
		self.assertEqual(frappe.db.count("Error Log", {"method": ["like", "Receipt:%"]}), before)

	def test_the_paid_receipt_shows_the_same_and_logs_no_difference(self):
		self._pay(self.first, 2211)
		before = frappe.db.count("Error Log", {"method": ["like", "Receipt:%"]})
		for invoice in (self.first, self.second):
			page = text(render(invoice))
			self.assertIn("¥201", page)
			self.assertIn("¥2,211", page)
		self.assertEqual(frappe.db.count("Error Log", {"method": ["like", "Receipt:%"]}), before)


class TestMergedBillMoneyAndNumbers(TestMergedTaxIsRoundedOnce):
	"""The same pair (two bills of 1,005 + tax: 2,211 together) seen through the change, the shift and the numbers a
	cashier reads before paying (found in the browser test 2026-11-10: change 690 instead of 689; the detail said 3,310
	while the payment said 3,311)."""

	def _values(self, name, *fields):
		return frappe.db.get_value("POS Invoice", name, list(fields), as_dict=True)

	def _pay_cash(self, invoice, handed_over):
		"""Settle with `handed_over` in cash (more than due: there is change); the dialog tells the server the amount due."""
		from ury.ury.doctype.ury_order.ury_order import make_invoice

		doc = frappe.get_doc("POS Invoice", invoice)
		print_bill(invoice, CASHIER)
		profile = frappe.get_doc("POS Profile", POS_PROFILE)
		with as_user(CASHIER):
			make_invoice(
				customer=doc.customer,
				payments=[{"mode_of_payment": profile.payments[0].mode_of_payment, "amount": handed_over}],
				cashier=CASHIER, pos_profile=POS_PROFILE, owner=CASHIER, table=doc.restaurant_table,
				invoice=invoice, expected_total=2211,
			)

	# --- the change -----------------------------------------------------------------

	def test_the_change_is_the_cash_over_the_merged_amount_clicking_the_first(self):
		self._pay_cash(self.first, 2500)
		first, second = (self._values(n, "paid_amount", "change_amount", "rounded_total") for n in (self.first, self.second))
		self.assertEqual(first.change_amount + second.change_amount, 289)
		for bill in (first, second):
			self.assertEqual(bill.paid_amount - bill.change_amount, bill.rounded_total)

	def test_the_change_is_the_same_clicking_the_second(self):
		self._pay_cash(self.second, 2500)
		first, second = (self._values(n, "paid_amount", "change_amount", "rounded_total") for n in (self.first, self.second))
		self.assertEqual(first.change_amount + second.change_amount, 289)
		for bill in (first, second):
			self.assertEqual(bill.paid_amount - bill.change_amount, bill.rounded_total)

	def test_the_receipt_says_the_same_change(self):
		self._pay_cash(self.first, 2500)
		for invoice in (self.first, self.second):
			page = text(render(invoice))
			self.assertIn("お預かり | ¥2,500", page)
			self.assertIn("合計（税込） | ¥2,211", page)
			self.assertIn("お釣り | ¥289", page)  # 2,500 - 2,211: the receipt adds up

	def test_the_cash_of_the_shift_is_what_the_shop_kept(self):
		self._pay_cash(self.first, 2500)
		closing = close_shift(self.opening)
		cash = next(row for row in closing.payment_reconciliation if row.mode_of_payment == "Cash")
		self.assertEqual(cash.expected_amount, 2211)

	# --- the numbers before paying ---------------------------------------------------------------

	def test_the_saved_drafts_have_the_amounts_of_the_pair(self):
		first = self._values(self.first, "rounded_total", "custom_merged_total")
		second = self._values(self.second, "rounded_total", "custom_merged_total")
		self.assertEqual((first.rounded_total, second.rounded_total), (1105, 1106))
		# what each bill says about the other one: together they are 2,211 whichever is opened
		self.assertEqual(first.rounded_total + first.custom_merged_total, 2211)
		self.assertEqual(second.rounded_total + second.custom_merged_total, 2211)

	def test_a_dish_added_later_keeps_the_pair_consistent(self):
		place_order(CASHIER, [(FOOD_ITEM, 2)], table=TABLES[0], invoice=self.first)
		first = self._values(self.first, "rounded_total", "custom_merged_total")
		second = self._values(self.second, "rounded_total", "custom_merged_total")
		with as_user(CASHIER):
			combined = preview_order_totals(self.first)["rounded_total"]
		self.assertEqual(first.rounded_total + second.rounded_total, combined)
		self.assertEqual(first.rounded_total + first.custom_merged_total, combined)
		self.assertEqual(second.rounded_total + second.custom_merged_total, combined)

	def test_the_order_list_shows_the_pair_amount(self):
		from ury.ury_pos.api import getPosInvoice

		with as_user(CASHIER):
			rows = getPosInvoice("Unbilled", 50, 0)["data"]
		card = next(row for row in rows if row["name"] in (self.first, self.second))
		self.assertEqual(card["rounded_total"] + round(card["custom_merged_total"]), 2211)

	# --- the pair comes apart ----------------------------------------------------------------------

	def test_after_unmerging_each_saved_draft_is_rounded_by_itself_again(self):
		with as_user(CASHIER):
			unmerge_bills(self.first)
		first, second = self._values(self.first, "rounded_total", "custom_merged_total"), self._values(
			self.second, "rounded_total", "custom_merged_total"
		)
		self.assertEqual((first.rounded_total, second.rounded_total), (1105, 1105))
		self.assertEqual((first.custom_merged_total or 0, second.custom_merged_total or 0), (0, 0))

	def test_cancelling_the_bill_made_first_gives_the_other_its_own_rounding_back(self):
		from ury.ury.doctype.ury_order.ury_order import cancel_order

		with as_user(CASHIER):
			cancel_order(self.first, "test")
		self.assertEqual(self._values(self.second, "rounded_total").rounded_total, 1105)

	def test_cancelling_the_bill_made_later_leaves_the_first_as_it_was(self):
		from ury.ury.doctype.ury_order.ury_order import cancel_order

		with as_user(CASHIER):
			cancel_order(self.second, "test")
		self.assertEqual(self._values(self.first, "rounded_total").rounded_total, 1105)

	# --- a discount on the saved drafts --------------------------------------------------------------

	def test_a_discount_on_the_saved_drafts_keeps_the_pair_rule(self):
		for name in (self.first, self.second):
			doc = frappe.get_doc("POS Invoice", name)
			doc.additional_discount_percentage = 10
			doc.save()
		first = self._values(self.first, "net_total", "total_taxes_and_charges", "rounded_total")
		second = self._values(self.second, "net_total", "total_taxes_and_charges", "rounded_total")
		net = first.net_total + second.net_total
		self.assertEqual(first.total_taxes_and_charges + second.total_taxes_and_charges, (net * 10) // 100)
		with as_user(CASHIER):
			combined = preview_order_totals(self.first, 10)["rounded_total"]
		self.assertEqual(first.rounded_total + second.rounded_total, combined)
