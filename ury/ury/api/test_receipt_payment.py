"""What the receipt says about the payment (税理士, 2026-11-09): the payment method, a note when a credit card paid, and the
place for a 収入印紙 when cash of 50,000 yen or more (without the consumption tax) was received. Run on the test site only."""

import unittest

import frappe

from ury.setup.jp_tax import refresh_receipt_format
from ury.setup.test_site import CASHIER, FOOD_ITEM, TABLES, URYFlowTestCase, open_pos, pay_with, place_order
from ury.ury.api.receipt import STAMP_THRESHOLD, stamp_duty_needed
from ury.ury.api.test_receipt import render, text

CREDIT_NOTE = "※クレジットカードによる信用取引の決済です"
STAMP_BOX = "収入印紙 貼付欄"


class TestTheStampRule(unittest.TestCase):
	"""Cash received (change taken off), counted without the tax: 50,000 yen or more needs a stamp on a paper receipt."""

	def test_the_threshold_is_fifty_thousand(self):
		self.assertEqual(STAMP_THRESHOLD, 50000)

	def test_all_cash_counts_the_amount_without_the_tax(self):
		self.assertTrue(stamp_duty_needed(cash_paid=55000, net_total=50000, total=55000))
		self.assertFalse(stamp_duty_needed(cash_paid=54998, net_total=49999, total=54998))

	def test_no_cash_no_stamp(self):
		self.assertFalse(stamp_duty_needed(cash_paid=0, net_total=100000, total=110000))

	def test_a_mixed_payment_takes_the_cash_part_by_the_share_without_tax(self):
		self.assertTrue(stamp_duty_needed(cash_paid=55000, net_total=100000, total=110000))  # 55,000 x 100,000/110,000 = 50,000
		self.assertFalse(stamp_duty_needed(cash_paid=54000, net_total=100000, total=110000))  # 49,090

	def test_nothing_to_divide_by_is_no_stamp(self):
		self.assertFalse(stamp_duty_needed(cash_paid=60000, net_total=0, total=0))


class TestReceiptPayment(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		original = frappe.db.get_value("Item Price", {"item_code": FOOD_ITEM, "selling": 1}, "price_list_rate")
		self.addCleanup(self._set_price, original)
		refresh_receipt_format()
		frappe.db.commit()
		open_pos(CASHIER)

	def _set_price(self, price):
		frappe.db.sql("update `tabItem Price` set price_list_rate = %s where item_code = %s and selling = 1", (price, FOOD_ITEM))
		frappe.db.commit()

	def _paid(self, price, payments):
		self._set_price(price)
		order = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])
		pay_with(order, payments)
		return text(render(order))

	# --- the method ---------------------------------------------------------------

	def test_cash_only_says_cash(self):
		out = self._paid(1000, [("Cash", 1100)])
		self.assertIn("お支払方法 | Cash", out)
		self.assertNotIn(CREDIT_NOTE, out)

	def test_a_card_says_the_card_and_that_it_is_a_credit_transaction(self):
		out = self._paid(1000, [("クレジットカード", 1100)])
		self.assertIn("お支払方法 | クレジットカード", out)
		self.assertIn(CREDIT_NOTE, out)

	def test_a_wallet_is_shown_by_its_name_without_the_credit_note(self):
		out = self._paid(1000, [("PayPay", 1100)])
		self.assertIn("お支払方法 | PayPay", out)
		self.assertNotIn(CREDIT_NOTE, out)

	def test_cash_and_card_list_both(self):
		out = self._paid(1000, [("Cash", 500), ("クレジットカード", 600)])
		self.assertIn("お支払方法 | Cash、クレジットカード", out)
		self.assertIn(CREDIT_NOTE, out)

	def test_before_the_payment_there_is_nothing_of_it(self):
		self._set_price(1000)
		order = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])
		out = text(render(order))
		self.assertNotIn("お支払方法", out)
		self.assertNotIn(CREDIT_NOTE, out)
		self.assertNotIn(STAMP_BOX, out)

	# --- the stamp --------------------------------------------------------------------

	def test_cash_of_fifty_thousand_without_tax_gets_the_place_for_a_stamp(self):
		out = self._paid(50000, [("Cash", 55000)])
		self.assertIn(STAMP_BOX, out)

	def test_change_is_taken_off_the_cash_received(self):
		out = self._paid(50000, [("Cash", 60000)])  # 5,000 back: 55,000 paid
		self.assertIn(STAMP_BOX, out)
		out = self._paid(40000, [("Cash", 60000)])  # 44,000 paid
		self.assertNotIn(STAMP_BOX, out)

	def test_a_yen_less_than_fifty_thousand_without_tax_has_none(self):
		out = self._paid(49999, [("Cash", 54998)])
		self.assertNotIn(STAMP_BOX, out)

	def test_a_card_has_none_however_large(self):
		out = self._paid(100000, [("クレジットカード", 110000)])
		self.assertNotIn(STAMP_BOX, out)

	def test_the_cash_part_of_a_mixed_payment_counts_by_its_share_without_tax(self):
		self.assertIn(STAMP_BOX, self._paid(100000, [("Cash", 55000), ("クレジットカード", 55000)]))
		self.assertNotIn(STAMP_BOX, self._paid(100000, [("Cash", 54000), ("クレジットカード", 56000)]))
