"""Paying with cash, cashless methods or both (docs/design/cashless-payment-design.md).

Money over the amount due is change, and change is only given in cash. Run on the test site only.
"""

import frappe

from ury.setup.cashless import apply_cashless_payments
from ury.setup.test_site import (
	ABBR,
	ALCOHOL_ITEM,
	CASHIER,
	FOOD_ITEM,
	TABLES,
	URYFlowTestCase,
	_closing_rows,
	as_user,
	close_shift,
	open_pos,
	pay_with,
	place_order,
)
from ury.ury_pos.api import merge_bills

CARD = "クレジットカード"
PAYPAY = "PayPay"
CARD_ACCOUNT = f"売掛金（カード会社） - {ABBR}"
RAKUTEN_ACCOUNT = f"売掛金（楽天ペイ） - {ABBR}"


class CashlessTestCase(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		apply_cashless_payments()
		frappe.db.commit()
		self.opening = open_pos(CASHIER)

	def order(self, table=0, items=((FOOD_ITEM, 1),)):
		return place_order(CASHIER, list(items), table=TABLES[table])


class TestChangeIsCashOnly(CashlessTestCase):
	def test_exact_card_payment(self):
		invoice = pay_with(self.order(), [(CARD, 1100)])
		self.assertEqual([(p.mode_of_payment, p.amount) for p in invoice.payments], [(CARD, 1100)])
		self.assertEqual(invoice.change_amount, 0)

	def test_a_card_cannot_be_charged_more_than_the_amount_due(self):
		order = self.order()
		with self.assertRaises(frappe.ValidationError):
			pay_with(order, [(CARD, 2000)])
		self.assertEqual(frappe.db.get_value("POS Invoice", order, "docstatus"), 0)

	def test_a_wallet_cannot_be_charged_more_than_the_amount_due(self):
		order = self.order()
		with self.assertRaises(frappe.ValidationError):
			pay_with(order, [(PAYPAY, 1101)])
		self.assertEqual(frappe.db.get_value("POS Invoice", order, "docstatus"), 0)

	def test_cash_over_the_amount_gives_change(self):
		invoice = pay_with(self.order(), [("Cash", 2000)])
		self.assertEqual(invoice.change_amount, 900)

	def test_cash_and_card_adding_up_exactly(self):
		invoice = pay_with(self.order(), [("Cash", 500), (CARD, 600)])
		self.assertEqual(sorted((p.mode_of_payment, p.amount) for p in invoice.payments), sorted([("Cash", 500), (CARD, 600)]))
		self.assertEqual(invoice.change_amount, 0)

	def test_change_comes_out_of_the_cash_when_card_is_paid_too(self):
		invoice = pay_with(self.order(), [("Cash", 1000), (CARD, 600)])
		self.assertEqual(invoice.change_amount, 500)

	def test_change_up_to_the_cash_handed_over_is_fine(self):
		invoice = pay_with(self.order(), [("Cash", 100), (CARD, 1100)])
		self.assertEqual(invoice.change_amount, 100)

	def test_change_cannot_be_more_than_the_cash_handed_over(self):
		order = self.order()
		with self.assertRaises(frappe.ValidationError):
			pay_with(order, [("Cash", 100), (CARD, 1200)])
		self.assertEqual(frappe.db.get_value("POS Invoice", order, "docstatus"), 0)

	def test_a_short_payment_is_still_refused(self):
		with self.assertRaises(frappe.ValidationError):
			pay_with(self.order(), [(CARD, 1000)])


class TestMergedBillByCard(CashlessTestCase):
	def setUp(self):
		super().setUp()
		self.first = self.order(0, [(FOOD_ITEM, 1)])
		self.second = self.order(1, [(ALCOHOL_ITEM, 1)])
		with as_user(CASHIER):
			merge_bills(self.first, self.second)

	def test_a_card_pays_both_bills_each_for_its_own_amount(self):
		pay_with(self.first, [(CARD, 1650)], expected_total=1650)
		rows = {
			name: [(p.mode_of_payment, p.amount) for p in frappe.get_doc("POS Invoice", name).payments]
			for name in (self.first, self.second)
		}
		self.assertEqual(rows, {self.first: [(CARD, 1100)], self.second: [(CARD, 550)]})

	def test_card_and_cash_split_over_the_two_bills(self):
		pay_with(self.first, [("Cash", 1200), (CARD, 450)], expected_total=1650)
		paid = [frappe.get_doc("POS Invoice", name) for name in (self.first, self.second)]
		by_mode = {}
		for invoice in paid:
			for p in invoice.payments:
				by_mode[p.mode_of_payment] = by_mode.get(p.mode_of_payment, 0) + p.amount
		self.assertEqual(by_mode, {"Cash": 1200, CARD: 450})
		self.assertEqual(sum(i.change_amount for i in paid), 0)

	def test_card_cannot_be_charged_over_a_merged_bill(self):
		with self.assertRaises(frappe.ValidationError):
			pay_with(self.first, [(CARD, 2000)], expected_total=1650)


class TestCashlessInTheShift(CashlessTestCase):
	def test_expected_per_mode_has_no_opening_amount_and_no_change_for_cashless(self):
		cash = pay_with(self.order(0), [("Cash", 1500)])  # 1,100 due, 400 change
		card = pay_with(self.order(1), [(CARD, 1100)])
		mixed = pay_with(self.order(2), [("Cash", 1000), (PAYPAY, 600)])  # 1,100 due, 500 change
		_totals, _taxes, payments = _closing_rows(self.opening, [cash, card, mixed])
		expected = {p["mode_of_payment"]: p["expected_amount"] - p["opening_amount"] for p in payments}
		self.assertEqual(expected, {"Cash": (1500 - 400) + (1000 - 500), CARD: 1100, PAYPAY: 600})

	def test_the_closing_posts_each_mode_to_its_account(self):
		invoices = [
			pay_with(self.order(0), [("Cash", 1500)]),
			pay_with(self.order(1), [(CARD, 1100)]),
			pay_with(self.order(2), [("Cash", 1000), (PAYPAY, 600)]),
		]
		closing = close_shift(self.opening)
		sales_invoices = {
			frappe.db.get_value("POS Invoice Merge Log", log.name, "consolidated_invoice")
			for log in frappe.get_all("POS Invoice Merge Log", filters={"pos_closing_entry": closing.name})
		}
		gl = frappe.get_all(
			"GL Entry",
			filters={"voucher_no": ["in", list(sales_invoices)], "is_cancelled": 0},
			fields=["account", "debit", "credit"],
		)
		debit = lambda account: sum(row.debit - row.credit for row in gl if row.account == account)
		self.assertEqual(debit(CARD_ACCOUNT), 1100)
		self.assertEqual(debit(RAKUTEN_ACCOUNT), 600)
		# cash: 1,500 + 1,000 handed over, less the change of 400 and 500
		self.assertEqual(debit(f"Cash - {ABBR}"), 1100 + 500)
		self.assertAlmostEqual(sum(row.debit for row in gl), sum(row.credit for row in gl), places=2)
