"""Merged bills (会計合算): two open orders paid and printed as one.

Both invoices stay separate documents that point at each other (`merge_bills`); whichever is
paid, both are settled, each for its own amount. docs/design/pos-closing.md and
docs/design/jp-tax-design.md (J10). Run on the test site only.
"""

import frappe

from ury.setup.jp_tax import RECEIPT_FORMAT, refresh_receipt_format
from ury.setup.test_site import (
	ALCOHOL_ITEM,
	CASHIER,
	FOOD_ITEM,
	MANAGER,
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
from ury.ury.api.test_receipt import render, text
from ury.ury_pos.api import getPosInvoice, merge_bills


class TestMergedBill(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		original = frappe.db.get_value("POS Profile", POS_PROFILE, ["apply_discount_on", "custom_enable_discount"])
		self.addCleanup(self._set_discount, *original)
		self._set_discount("Net Total", 1)
		refresh_receipt_format()
		frappe.db.commit()
		self.opening = open_pos(CASHIER)
		# 1,000 at table T-01, 500 at table T-02: 1,100 + 550 = 1,650 with 10% tax
		self.first = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])
		self.second = place_order(CASHIER, [(ALCOHOL_ITEM, 1)], table=TABLES[1])
		with as_user(CASHIER):
			merge_bills(self.first, self.second)

	def _set_discount(self, apply_on, enabled):
		frappe.db.set_value("POS Profile", POS_PROFILE, {"apply_discount_on": apply_on, "custom_enable_discount": enabled})
		frappe.db.commit()
		frappe.clear_document_cache("POS Profile", POS_PROFILE)

	def _preview(self, invoice, discount=None):
		with as_user(CASHIER):
			return preview_order_totals(invoice, discount)

	def _pay(self, invoice, amount, discount=None):
		"""Settle the way the payment dialog does: one payment of the amount it shows."""
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
			)

	def _values(self, name, *fields):
		return frappe.db.get_value("POS Invoice", name, list(fields), as_dict=True)

	def _orders(self, status="Unbilled"):
		with as_user(CASHIER):
			return getPosInvoice(status, 50, 0)["data"]

	# --- the amount the payment dialog shows ------------------------------------

	def test_the_preview_of_either_bill_is_the_combined_amount(self):
		for invoice in (self.first, self.second):
			totals = self._preview(invoice)
			self.assertEqual((totals["total"], totals["net_total"], totals["rounded_total"]), (1500, 1500, 1650))
			self.assertEqual(
				[(t["rate"], t["taxable_amount"], t["tax_amount"]) for t in totals["taxes"]], [(10, 1500, 150)]
			)

	def test_a_bill_that_is_not_merged_still_shows_only_itself(self):
		other = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[2])
		self.assertEqual(self._preview(other)["rounded_total"], 1100)

	# --- paying ----------------------------------------------------------------

	def test_paying_the_amount_of_the_dialog_settles_both(self):
		amount = self._preview(self.first)["rounded_total"]
		self._pay(self.first, amount)
		first, second = self._values(self.first, "docstatus", "status", "paid_amount", "rounded_total"), self._values(
			self.second, "docstatus", "status", "paid_amount", "rounded_total"
		)
		self.assertEqual((first.docstatus, first.status, second.docstatus, second.status), (1, "Paid", 1, "Paid"))
		self.assertEqual((first.rounded_total, second.rounded_total), (1100, 550))
		self.assertEqual(first.paid_amount + second.paid_amount, amount)

	def test_paying_the_other_bill_works_the_same(self):
		amount = self._preview(self.second)["rounded_total"]
		self._pay(self.second, amount)
		for name in (self.first, self.second):
			self.assertEqual(self._values(name, "status").status, "Paid")

	def test_the_shift_counts_both_bills_once(self):
		self._pay(self.first, self._preview(self.first)["rounded_total"])
		closing = close_shift(self.opening)
		self.assertEqual({row.pos_invoice for row in closing.pos_transactions}, {self.first, self.second})
		self.assertEqual(sum(row.grand_total for row in closing.pos_transactions), 1650)
		self.assertEqual(sum(p.expected_amount for p in closing.payment_reconciliation), 1650)
		self.assertEqual(closing.grand_total, 1650)
		self.assertEqual(sum(t.amount for t in closing.taxes), 150)

	# --- a discount ------------------------------------------------------------

	def test_a_percentage_discount_is_taken_off_both(self):
		totals = self._preview(self.first, 10)
		self.assertEqual((totals["net_total"], totals["discount_amount"], totals["rounded_total"]), (1350, 150, 1485))
		self.assertEqual([(t["taxable_amount"], t["tax_amount"]) for t in totals["taxes"]], [(1350, 135)])

		self._pay(self.first, totals["rounded_total"], discount=10)
		first = self._values(self.first, "status", "rounded_total", "additional_discount_percentage")
		second = self._values(self.second, "status", "rounded_total", "additional_discount_percentage")
		self.assertEqual((first.status, second.status), ("Paid", "Paid"))
		self.assertEqual((first.additional_discount_percentage, second.additional_discount_percentage), (10, 10))
		self.assertEqual(first.rounded_total + second.rounded_total, 1485)

	# --- the amounts stay current ---------------------------------------------------

	def test_adding_an_item_to_one_bill_updates_the_other(self):
		place_order(CASHIER, [(ALCOHOL_ITEM, 3)], table=TABLES[1], invoice=self.second)  # 1,500 -> 1,650
		self.assertEqual(self._preview(self.first)["rounded_total"], 1100 + 1650)
		self.assertEqual(self._values(self.first, "custom_merged_total").custom_merged_total, 1650)
		first = next(o for o in self._orders() if o["name"] in (self.first, self.second))
		self.assertEqual(first["rounded_total"] + first["custom_merged_total"], 2750)

		place_order(CASHIER, [(FOOD_ITEM, 2)], table=TABLES[0], invoice=self.first)  # 1,100 -> 2,200
		self.assertEqual(self._values(self.second, "custom_merged_total").custom_merged_total, 2200)
		self.assertEqual(self._preview(self.second)["rounded_total"], 2200 + 1650)
		details = frappe.get_all("URY Merged POS Invoice Detail", filters={"parent": self.second}, fields=["qty"])
		self.assertEqual([d.qty for d in details], [2])

	def test_paying_after_an_item_was_added(self):
		place_order(CASHIER, [(ALCOHOL_ITEM, 3)], table=TABLES[1], invoice=self.second)
		amount = self._preview(self.first)["rounded_total"]
		self._pay(self.first, amount)
		self.assertEqual(self._values(self.second, "status", "rounded_total"), {"status": "Paid", "rounded_total": 1650})

	# --- the list --------------------------------------------------------------

	def test_the_list_shows_one_card_for_a_merged_bill(self):
		single = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[2])
		names = [o["name"] for o in self._orders()]
		self.assertIn(single, names)
		self.assertEqual(len({self.first, self.second} & set(names)), 1)
		card = next(o for o in self._orders() if o["name"] in (self.first, self.second))
		other = self.second if card["name"] == self.first else self.first
		self.assertEqual(card["custom_merged_pos_invoice"], other)
		self.assertEqual(card["merged_table"], frappe.db.get_value("POS Invoice", other, "restaurant_table"))
		self.assertEqual(card["rounded_total"] + card["custom_merged_total"], 1650)

	def test_the_card_is_the_one_made_first(self):
		card = next(o for o in self._orders() if o["name"] in (self.first, self.second))
		self.assertEqual(card["name"], self.first)

	def test_the_paid_bills_are_one_card_too(self):
		self._pay(self.first, 1650)
		paid = [o["name"] for o in self._orders("Recently Paid") if o["name"] in (self.first, self.second)]
		self.assertEqual(paid, [self.first])

	# --- cancelling one ---------------------------------------------------------

	def test_cancelling_one_bill_unmerges_the_other(self):
		from ury.ury.doctype.ury_order.ury_order import cancel_order

		with as_user(MANAGER):
			cancel_order(self.first, "test")
		self.assertEqual(self._values(self.first, "docstatus").docstatus, 2)
		second = self._values(self.second, "docstatus", "custom_merged_pos_invoice", "custom_merged_total")
		self.assertEqual(second.docstatus, 0)
		self.assertFalse(second.custom_merged_pos_invoice)
		self.assertFalse(second.custom_merged_total)
		self.assertEqual(frappe.db.count("URY Merged POS Invoice Detail", {"parent": self.second}), 0)
		# it is an ordinary bill again: its own amount only, and it can be paid on its own
		self.assertEqual(self._preview(self.second)["rounded_total"], 550)
		self._pay(self.second, 550)
		self.assertEqual(self._values(self.second, "status").status, "Paid")
		card = next(o for o in self._orders("Recently Paid") if o["name"] == self.second)
		self.assertFalse(card["custom_merged_pos_invoice"])

	# --- a bill that is paid or cancelled is not touched ----------------------------

	def _snapshot(self, name):
		doc = self._values(name, "docstatus", "status", "custom_merged_pos_invoice", "custom_merged_total", "modified")
		details = frappe.get_all(
			"URY Merged POS Invoice Detail", filters={"parent": name}, fields=["item_code", "qty", "amount"], order_by="idx"
		)
		return doc, details

	def test_cancelling_a_paid_merged_bill_is_refused_and_changes_nothing(self):
		"""ERPNext does not cancel a bill another submitted bill links to; the other bill must not be
		edited to get around that. The refusal comes before tables or KOT are touched."""
		from ury.ury.doctype.ury_order.ury_order import cancel_order

		self._pay(self.first, 1650)
		before = (self._snapshot(self.first), self._snapshot(self.second))
		with as_user(MANAGER), self.assertRaises(frappe.ValidationError) as caught:
			cancel_order(self.first, "test")
		self.assertIn(self.second, str(caught.exception))
		self.assertEqual((self._snapshot(self.first), self._snapshot(self.second)), before)

	def test_the_other_bill_is_not_refreshed_when_it_is_paid_or_cancelled(self):
		from ury.ury.hooks.ury_pos_invoice import refresh_merged_snapshot

		for docstatus, status in ((1, "Paid"), (2, "Cancelled")):
			frappe.db.set_value("POS Invoice", self.second, {"docstatus": docstatus, "status": status}, update_modified=False)
			before = self._snapshot(self.second)
			first = frappe.get_doc("POS Invoice", self.first)
			first.items[0].qty = 5  # the snapshot would change if it were refreshed
			refresh_merged_snapshot(first)
			self.assertEqual(self._snapshot(self.second), before, status)

	def test_saving_a_bill_does_not_save_a_paid_partner(self):
		frappe.db.set_value("POS Invoice", self.second, {"docstatus": 1, "status": "Paid"}, update_modified=False)
		before = self._snapshot(self.second)
		place_order(CASHIER, [(FOOD_ITEM, 2)], table=TABLES[0], invoice=self.first)
		self.assertEqual(self._snapshot(self.second), before)

	# --- the receipt -------------------------------------------------------------

	def test_the_receipt_reads_the_other_bill_as_it_is_now(self):
		place_order(CASHIER, [(ALCOHOL_ITEM, 3)], table=TABLES[1], invoice=self.second)
		for invoice in (self.first, self.second):
			out = text(render(invoice))
			self.assertIn("10%対象（税抜） | ¥2,500", out)
			self.assertIn("合計（税込） | ¥2,750", out)
			self.assertIn(f"{ALCOHOL_ITEM}", out)

	def test_the_receipt_after_payment(self):
		self._pay(self.first, 1650)
		out = text(render(self.first))
		self.assertIn("領収書", out)
		self.assertIn("合計（税込） | ¥1,650", out)
		self.assertIn("お預かり | ¥1,650", out)
		self.assertNotIn("お釣り", out)
