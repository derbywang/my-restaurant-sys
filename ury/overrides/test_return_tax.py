"""The tax of a return (Credit Note) of a POS Invoice.

ERPNext copies the tax rows of the original into the return and calculates them again on a NEGATIVE amount; cutting
-150.5 down gives -151 while the original, cut down from +150.5, has 150. So the shop paid back a yen of tax (and of cash)
more than it had been paid. The rules (docs/design/jp-tax-design.md, returns):

* a return of the WHOLE invoice has exactly the tax of the original, row by row (also the bill made later of a merged pair,
  whose tax is its part of the tax of the merged bill);
* a PART of an invoice is taxed on the absolute amount, cut once per rate the way the shop configured, then made negative.

Only returns (`is_return`) are different; the tax of a sale is not touched (test_pos_invoice.py).

These tests write data (orders, payments, returns, a closing): run them on a trial site first (scripts/trial_run.sh).
"""

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime

from ury.setup.test_site import (
	ABBR,
	ALCOHOL_ITEM,
	CASHIER,
	CUSTOMER,
	FOOD_ITEM,
	POS_PROFILE,
	PRICE_LIST,
	TABLES,
	URYFlowTestCase,
	as_user,
	close_shift,
	open_pos,
	pay_order,
	place_order,
	print_bill,
)

PRICE = 1505  # tax-exclusive: 10% is 150.5 and 8% is 120.4, so the cut matters
TEN = f"仮受消費税等（10％） - {ABBR}"
EIGHT = f"仮受消費税等（軽減8％） - {ABBR}"


def tax_by_account(doc):
	return {row.account_head: row.tax_amount for row in doc.taxes if row.tax_amount}


class ReturnTaxCase(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		prices = frappe.get_all(
			"Item Price",
			filters={"price_list": PRICE_LIST, "item_code": ("in", (FOOD_ITEM, ALCOHOL_ITEM))},
			fields=["name", "price_list_rate"],
		)
		self.addCleanup(self._restore_prices, prices)
		for price in prices:
			frappe.db.set_value("Item Price", price.name, "price_list_rate", PRICE)
		mode = frappe.db.get_value("POS Profile", POS_PROFILE, "custom_tax_rounding")
		self.addCleanup(self._set_rounding, mode)
		self._set_rounding("Round Down")
		frappe.db.commit()
		frappe.clear_cache()
		self.opening = open_pos(CASHIER)

	def _restore_prices(self, prices):
		for price in prices:
			frappe.db.set_value("Item Price", price.name, "price_list_rate", price.price_list_rate)
		frappe.db.commit()
		frappe.clear_cache()

	def _set_rounding(self, mode):
		frappe.db.set_value("POS Profile", POS_PROFILE, "custom_tax_rounding", mode)
		frappe.db.commit()
		frappe.clear_document_cache("POS Profile", POS_PROFILE)
		frappe.clear_cache(doctype="POS Profile")

	# --- helpers -------------------------------------------------------------

	def sale(self, items, table=0, order_type="Dine In"):
		"""A paid POS Invoice (cash, exactly the amount due)."""
		order = place_order(CASHIER, items, table=TABLES[table], order_type=order_type, customer=CUSTOMER)
		return pay_order(order)

	def build_return(self, original, quantities=None):
		"""The return the Desk makes ("Create > Return / Credit Note"), refunded in cash as much as it says. `quantities`:
		{item: how many} for a part of the invoice, None for all of it. Not saved yet."""
		from erpnext.controllers.sales_and_purchase_return import make_return_doc

		ret = make_return_doc("POS Invoice", original)
		ret.pos_profile = POS_PROFILE
		# the clock of the dev container can step back: a return is never before the invoice it returns
		posted = get_datetime(f"{frappe.db.get_value('POS Invoice', original, 'posting_date')} {frappe.db.get_value('POS Invoice', original, 'posting_time')}")
		later = max(now_datetime(), add_to_date(posted, seconds=1))
		ret.set_posting_time = 1
		ret.posting_date, ret.posting_time = later.date(), later.time().strftime("%H:%M:%S")
		if quantities is not None:
			ret.set("items", [row for row in ret.items if row.item_code in quantities])
			for row in ret.items:
				row.qty = -quantities[row.item_code]
		ret.calculate_taxes_and_totals()
		ret.set("payments", [])
		refund = ret.rounded_total or ret.grand_total
		ret.append("payments", {"mode_of_payment": "Cash", "amount": refund})
		ret.paid_amount = ret.base_paid_amount = refund  # make_return_doc keeps the paid amount of the original
		return ret

	def submit_return(self, original, quantities=None):
		ret = self.build_return(original, quantities)
		with as_user(CASHIER):
			ret.flags.ignore_permissions = True
			ret.insert(ignore_permissions=True)
			ret.submit()
		frappe.db.commit()
		ret.reload()
		return ret

	def assert_returns_what_was_paid(self, original, ret):
		self.assertEqual(tax_by_account(ret), {k: -v for k, v in tax_by_account(original).items()})
		self.assertEqual(ret.grand_total, -original.grand_total)
		self.assertEqual(ret.paid_amount, -original.paid_amount)  # the cash given back is the cash that was taken

	def tax_accounts_net(self):
		"""Credit minus debit of the tax accounts, the cash and the sales, of the invoices the closing made."""
		closing = close_shift(self.opening)
		logs = frappe.get_all("POS Invoice Merge Log", filters={"pos_closing_entry": closing.name}, fields=["consolidated_invoice", "consolidated_credit_note"])
		vouchers = [name for log in logs for name in (log.consolidated_invoice, log.consolidated_credit_note) if name]
		self.assertTrue(vouchers)
		rows = frappe.db.sql(
			"""select account, sum(credit) - sum(debit) from `tabGL Entry`
			where voucher_no in %s and is_cancelled = 0 group by account""",
			(vouchers,),
		)
		return {account: round(net, 2) for account, net in rows}

	def assert_ledger_is_square(self):
		net = self.tax_accounts_net()
		self.assertEqual(net.get(TEN, 0), 0, net)
		self.assertEqual(net.get(EIGHT, 0), 0, net)
		self.assertEqual({a: v for a, v in net.items() if v}, {}, net)  # cash, sales, debtors: everything comes back to 0


class TestWholeInvoiceReturn(ReturnTaxCase):
	def test_dine_in_ten_percent(self):
		original = self.sale([(FOOD_ITEM, 1)])
		self.assertEqual(tax_by_account(original), {TEN: 150})
		ret = self.submit_return(original.name)
		self.assertEqual(tax_by_account(ret), {TEN: -150})
		self.assert_returns_what_was_paid(original, ret)
		self.assert_ledger_is_square()

	def test_take_away_reduced_rate(self):
		original = self.sale([(FOOD_ITEM, 1)], table=1, order_type="Take Away")
		self.assertEqual(tax_by_account(original), {EIGHT: 120})
		ret = self.submit_return(original.name)
		self.assertEqual(tax_by_account(ret), {EIGHT: -120})
		self.assert_returns_what_was_paid(original, ret)
		self.assert_ledger_is_square()

	def test_both_rates_in_one_invoice(self):
		original = self.sale([(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)], table=2, order_type="Take Away")
		self.assertEqual(tax_by_account(original), {EIGHT: 120, TEN: 150})
		ret = self.submit_return(original.name)
		self.assertEqual(tax_by_account(ret), {EIGHT: -120, TEN: -150})
		self.assert_returns_what_was_paid(original, ret)
		self.assert_ledger_is_square()

	def test_the_rounding_of_the_shop_is_the_one_of_the_original(self):
		"""The original was cut one way; the return has the same tax whatever the setting is now."""
		original = self.sale([(FOOD_ITEM, 1)])
		self._set_rounding("Round Up")
		ret = self.submit_return(original.name)
		self.assertEqual(tax_by_account(ret), {TEN: -150})
		self.assert_returns_what_was_paid(original, ret)

	def test_a_return_of_a_discounted_invoice(self):
		original_setting = frappe.db.get_value("POS Profile", POS_PROFILE, ["apply_discount_on", "custom_enable_discount"])
		self.addCleanup(self._discount, *original_setting)
		self._discount("Net Total", 1)
		order = place_order(CASHIER, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)], table=TABLES[0], customer=CUSTOMER)
		original = pay_order(order, discount=10)
		ret = self.submit_return(original.name)
		self.assert_returns_what_was_paid(original, ret)

	def _discount(self, apply_on, enabled):
		frappe.db.set_value("POS Profile", POS_PROFILE, {"apply_discount_on": apply_on, "custom_enable_discount": enabled})
		frappe.db.commit()
		frappe.clear_document_cache("POS Profile", POS_PROFILE)
		frappe.clear_cache(doctype="POS Profile")


class TestMergedPairReturn(ReturnTaxCase):
	def test_each_bill_of_a_merged_pair_returns_its_own_tax(self):
		from ury.ury.doctype.ury_order.ury_order import make_invoice
		from ury.ury_pos.api import merge_bills

		first = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0], customer=CUSTOMER)
		second = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[1], customer=CUSTOMER)
		made = frappe.db.get_value("POS Invoice", first, "creation")
		frappe.db.set_value("POS Invoice", second, "creation", add_to_date(made, seconds=1), update_modified=False)
		with as_user(CASHIER):
			merge_bills(first, second)
		print_bill(first)
		total = 3311  # (1505 + 1505) = 3010 and 10% of it is 301: 150 on the first bill, 151 on the second
		with as_user(CASHIER):
			make_invoice(
				customer=CUSTOMER,
				payments=[{"mode_of_payment": "Cash", "amount": total}],
				cashier=CASHIER,
				pos_profile=POS_PROFILE,
				owner=CASHIER,
				table=TABLES[0],
				invoice=first,
				expected_total=total,
			)
		originals = [frappe.get_doc("POS Invoice", name) for name in (first, second)]
		self.assertEqual([tax_by_account(o) for o in originals], [{TEN: 150}, {TEN: 151}])

		returns = [self.submit_return(o.name) for o in originals]
		self.assertEqual([tax_by_account(r) for r in returns], [{TEN: -150}, {TEN: -151}])
		self.assertEqual(sum(tax_by_account(r)[TEN] for r in returns), -301)
		for original, ret in zip(originals, returns):
			self.assertEqual(ret.grand_total, -original.grand_total)
		# the cash paid back is the cash taken: 3311 in, 3311 out
		self.assertEqual(sum(r.grand_total for r in returns), -total)
		self.assert_ledger_is_square()


class TestPartReturn(ReturnTaxCase):
	"""A part is taxed on the absolute amount, cut once per rate, then made negative."""

	def test_one_of_three_dishes(self):
		original = self.sale([(FOOD_ITEM, 3)])
		self.assertEqual(tax_by_account(original), {TEN: 451})  # floor(451.5)
		ret = self.submit_return(original.name, {FOOD_ITEM: 1})
		self.assertEqual(ret.net_total, -PRICE)
		self.assertEqual(tax_by_account(ret), {TEN: -150})  # not -151
		self.assertEqual(ret.grand_total, -(PRICE + 150))
		self.assertEqual(ret.paid_amount, ret.grand_total)

	def test_one_rate_of_a_mixed_invoice(self):
		original = self.sale([(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)], table=2, order_type="Take Away")
		ret = self.submit_return(original.name, {FOOD_ITEM: 1})
		self.assertEqual(tax_by_account(ret), {EIGHT: -120})
		ret2 = self.submit_return(original.name, {ALCOHOL_ITEM: 1})
		self.assertEqual(tax_by_account(ret2), {TEN: -150})

	def test_each_rate_is_cut_once(self):
		"""Two dishes of the same rate in two rows are one amount of that rate (not two cuts)."""
		original = self.sale([(FOOD_ITEM, 2), (ALCOHOL_ITEM, 2)], table=2, order_type="Take Away")
		ret = self.submit_return(original.name, {FOOD_ITEM: 1, ALCOHOL_ITEM: 1})
		self.assertEqual(tax_by_account(ret), {EIGHT: -120, TEN: -150})

	def test_the_cut_follows_the_setting_of_the_shop(self):
		original = self.sale([(FOOD_ITEM, 3)])
		for mode, expected in (("Round Down", -150), ("Round Half Up", -151), ("Round Up", -151)):
			self._set_rounding(mode)
			ret = self.build_return(original.name, {FOOD_ITEM: 1})
			self.assertEqual(tax_by_account(ret), {TEN: expected}, mode)

	def test_the_returns_of_one_invoice_never_have_more_tax_than_the_original(self):
		original = self.sale([(FOOD_ITEM, 3)])
		returns = [self.submit_return(original.name, {FOOD_ITEM: 1}) for _ in range(3)]
		taxes = [tax_by_account(r)[TEN] for r in returns]
		self.assertEqual(taxes, [-150, -150, -150])
		# 450 of 451: the sum of the parts can be a yen less than the whole (written in the training and the design), never more
		self.assertLessEqual(-sum(taxes), tax_by_account(original)[TEN])
		self.assertEqual(sum(r.net_total for r in returns), -original.net_total)

	def test_a_part_after_a_part_is_a_part(self):
		"""The rest of an invoice, when a part of it has been returned, is not 'the whole invoice': it is cut on its own."""
		original = self.sale([(FOOD_ITEM, 2)])
		self.assertEqual(tax_by_account(original), {TEN: 301})  # 2 x 1505 = 3010
		first = self.submit_return(original.name, {FOOD_ITEM: 1})
		self.assertEqual(tax_by_account(first), {TEN: -150})
		rest = self.build_return(original.name)
		self.assertEqual(rest.net_total, -PRICE)
		self.assertEqual(tax_by_account(rest), {TEN: -150})


class TestMoreThanWasSold(ReturnTaxCase):
	def test_more_dishes_than_were_sold_is_refused(self):
		original = self.sale([(FOOD_ITEM, 2)])
		ret = self.build_return(original.name)
		ret.items[0].qty = -3
		with as_user(CASHIER), self.assertRaises(frappe.ValidationError):
			ret.calculate_taxes_and_totals()
			ret.set("payments", [])
			ret.append("payments", {"mode_of_payment": "Cash", "amount": ret.grand_total})
			ret.insert(ignore_permissions=True)
			ret.submit()

	def test_a_second_return_over_the_rest_is_refused(self):
		original = self.sale([(FOOD_ITEM, 2)])
		self.submit_return(original.name, {FOOD_ITEM: 1})
		with as_user(CASHIER), self.assertRaises(frappe.ValidationError):
			ret = self.build_return(original.name, {FOOD_ITEM: 2})
			ret.insert(ignore_permissions=True)
			ret.submit()

	def test_a_higher_price_than_was_sold_is_refused(self):
		original = self.sale([(FOOD_ITEM, 1)])
		ret = self.build_return(original.name)
		ret.items[0].rate = PRICE + 100
		with as_user(CASHIER), self.assertRaises(frappe.ValidationError):
			ret.calculate_taxes_and_totals()
			ret.insert(ignore_permissions=True)
			ret.submit()


class TestASaleIsNotChanged(ReturnTaxCase):
	"""The new rules are for `is_return` only."""

	def test_the_tax_of_a_sale_is_cut_as_before(self):
		sale = self.sale([(FOOD_ITEM, 3)])
		self.assertEqual(tax_by_account(sale), {TEN: 451})
		again = frappe.get_doc("POS Invoice", sale.name)
		again.calculate_taxes_and_totals()
		self.assertEqual(tax_by_account(again), {TEN: 451})
