import datetime

import frappe

from ury.setup.test_site import (
	ALCOHOL_ITEM,
	CAPTAIN,
	CASHIER,
	CASHIER2,
	CUSTOMER,
	CUSTOMER2,
	FOOD_ITEM,
	POS_PROFILE,
	TABLES,
	URYFlowTestCase,
	as_user,
	close_shift,
	close_sub_shift,
	disable_multiple_cashier,
	enable_multiple_cashier,
	open_pos,
	pay_order,
	place_order,
	print_bill,
)
from ury.ury.api.pos_closing import unconsolidated_invoices


def merge_logs(closing):
	return frappe.get_all(
		"POS Invoice Merge Log",
		filters={"pos_closing_entry": closing.name},
		fields=["name", "consolidated_invoice"],
	)


class TestPOSClosing(URYFlowTestCase):
	"""The closing the way the URY POS makes it: the invoices are listed in pos_transactions."""

	def _paid_by_two_people(self):
		mine = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])
		by_captain = [
			place_order(CAPTAIN, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)], table=TABLES[1]),
			place_order(CAPTAIN, [(FOOD_ITEM, 2)], table=TABLES[2], order_type="Take Away"),
		]
		names = [mine, *by_captain]
		return names, [pay_order(name) for name in names]

	def test_every_invoice_is_consolidated_including_the_captains(self):
		opening = open_pos(CASHIER)
		names, paid = self._paid_by_two_people()

		closing = close_shift(opening)

		self.assertEqual({row.pos_invoice for row in closing.pos_transactions}, set(names))
		logs = merge_logs(closing)
		self.assertEqual(len(logs), 1)
		sales_invoice = frappe.get_doc("Sales Invoice", logs[0].consolidated_invoice)
		# the Sales Invoice carries exactly what the POS invoices did
		self.assertEqual(sales_invoice.grand_total, sum(p.grand_total for p in paid))
		for name in names:
			self.assertEqual(frappe.db.get_value("POS Invoice", name, "consolidated_invoice"), sales_invoice.name)

	def test_taxes_of_each_rate_add_up(self):
		opening = open_pos(CASHIER)
		names, paid = self._paid_by_two_people()
		closing = close_shift(opening)

		sales_invoice = frappe.get_doc("Sales Invoice", merge_logs(closing)[0].consolidated_invoice)
		expected = {}
		for invoice in paid:
			for row in invoice.taxes:
				expected[row.account_head] = expected.get(row.account_head, 0) + row.tax_amount
		got = {row.account_head: row.tax_amount for row in sales_invoice.taxes}
		self.assertEqual({k: v for k, v in got.items() if v}, {k: v for k, v in expected.items() if v})
		self.assertEqual(sum(p.amount for p in sales_invoice.payments), sum(p.grand_total for p in paid))

	def test_a_closing_without_invoice_details_is_rejected(self):
		opening = open_pos(CASHIER)
		names, _paid = self._paid_by_two_people()

		with self.assertRaises(frappe.ValidationError) as caught:
			close_shift(opening, keep_transactions=False)

		for name in names:
			self.assertIn(name, str(caught.exception))
		self.assertEqual(frappe.db.count("POS Invoice Merge Log"), 0)
		self.assertEqual(frappe.db.count("POS Closing Entry", {"docstatus": 1}), 0)

	def test_a_closing_missing_one_invoice_is_rejected(self):
		opening = open_pos(CASHIER)
		names, _paid = self._paid_by_two_people()

		with self.assertRaises(frappe.ValidationError) as caught:
			close_shift(opening, only=names[:2])

		self.assertIn(names[2], str(caught.exception))
		self.assertNotIn(names[0], str(caught.exception))
		self.assertEqual(frappe.db.count("POS Invoice Merge Log"), 0)

	def test_an_already_consolidated_invoice_cannot_be_listed_again(self):
		first_opening = open_pos(CASHIER)
		old = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])
		pay_order(old)
		close_shift(first_opening)
		self.assertTrue(frappe.db.get_value("POS Invoice", old, "consolidated_invoice"))

		second_opening = open_pos(CASHIER)
		new = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[1])
		pay_order(new)

		with self.assertRaises(frappe.ValidationError) as caught:
			close_shift(second_opening, extra=[old])
		self.assertIn("already consolidated", str(caught.exception))

		# without it the second closing consolidates only the new invoice
		closing = close_shift(second_opening)
		self.assertEqual([row.pos_invoice for row in closing.pos_transactions], [new])

	def test_a_shift_without_invoices_can_be_closed(self):
		opening = open_pos(CASHIER)
		closing = close_shift(opening)
		self.assertEqual((closing.docstatus, closing.status), (1, "Submitted"))
		self.assertEqual(merge_logs(closing), [])

	# The tests that depend on time use fixed timestamps (set directly on the documents),
	# not the clock.
	YESTERDAY = datetime.datetime(2026, 1, 1)

	def _at(self, hour, minute=0):
		return self.YESTERDAY.replace(hour=hour, minute=minute)

	def _set_posting(self, invoice, when):
		frappe.db.set_value(
			"POS Invoice", invoice, {"posting_date": when.date(), "posting_time": when.time()}, update_modified=False
		)

	def _set_creation(self, invoice, when):
		frappe.db.set_value("POS Invoice", invoice, "creation", when, update_modified=False)

	def _set_opening_start(self, opening, when):
		frappe.db.set_value("POS Opening Entry", opening.name, "period_start_date", when, update_modified=False)
		opening.reload()

	def test_an_order_taken_before_the_opening_time_and_paid_after_it_is_included(self):
		opening = open_pos(CASHIER)
		draft = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])
		self._set_creation(draft, self._at(9))
		self._set_opening_start(opening, self._at(10))
		pay_order(draft)  # posted now, after the opening time
		self.assertLess(frappe.db.get_value("POS Invoice", draft, "creation"), opening.period_start_date)

		closing = close_shift(opening)

		self.assertEqual([row.pos_invoice for row in closing.pos_transactions], [draft])
		self.assertTrue(frappe.db.get_value("POS Invoice", draft, "consolidated_invoice"))

	def test_an_invoice_posted_before_the_opening_time_that_was_never_consolidated_is_included(self):
		# e.g. left out by an earlier closing: there is no lower time bound
		opening = open_pos(CASHIER)
		left_over = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])
		pay_order(left_over)
		self._set_posting(left_over, self._at(9))
		self._set_opening_start(opening, self._at(10))

		closing = close_shift(opening)

		self.assertEqual([row.pos_invoice for row in closing.pos_transactions], [left_over])

	def test_an_invoice_posted_after_the_closing_time_waits_for_the_next_shift(self):
		open_pos(CASHIER)
		first = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])
		later = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[1])
		pay_order(first)
		pay_order(later)
		self._set_posting(first, self._at(10))
		self._set_posting(later, self._at(11))

		self.assertEqual(unconsolidated_invoices(POS_PROFILE, self._at(10, 30)), [first])
		# the closing time itself is included
		self.assertEqual(unconsolidated_invoices(POS_PROFILE, self._at(10)), [first])
		self.assertEqual(unconsolidated_invoices(POS_PROFILE, self._at(9)), [])
		self.assertEqual(unconsolidated_invoices(POS_PROFILE, self._at(12)), [first, later])

	def test_customers_get_one_sales_invoice_each_and_the_totals_add_up(self):
		opening = open_pos(CASHIER)
		orders = [
			place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0], customer=CUSTOMER),
			place_order(CAPTAIN, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)], table=TABLES[1], order_type="Take Away", customer=CUSTOMER2),
			place_order(CAPTAIN, [(FOOD_ITEM, 2)], table=TABLES[2], customer=CUSTOMER2),
		]
		paid = [pay_order(name) for name in orders]

		closing = close_shift(opening)

		logs = merge_logs(closing)
		self.assertEqual(len(logs), 2)  # one per customer
		invoices = {log.name: frappe.get_doc("Sales Invoice", log.consolidated_invoice) for log in logs}
		self.assertEqual({si.customer for si in invoices.values()}, {CUSTOMER, CUSTOMER2})

		def taxes_of(docs):
			total = {}
			for doc in docs:
				for row in doc.taxes:
					total[row.account_head] = total.get(row.account_head, 0) + row.tax_amount
			return {account: amount for account, amount in total.items() if amount}

		# each Sales Invoice is the sum of its customer's POS invoices ...
		for sales_invoice in invoices.values():
			own = [p for p in paid if p.customer == sales_invoice.customer]
			self.assertEqual(sales_invoice.grand_total, sum(p.grand_total for p in own))
			self.assertEqual(taxes_of([sales_invoice]), taxes_of(own))
			self.assertEqual(sum(p.amount for p in sales_invoice.payments), sum(p.grand_total for p in own))
		# ... and together they are all of them
		self.assertEqual(sum(si.grand_total for si in invoices.values()), sum(p.grand_total for p in paid))
		self.assertEqual(taxes_of(invoices.values()), taxes_of(paid))
		for si in invoices.values():
			self.assertEqual(si.outstanding_amount, 0)


class TestDeskClosingForm(URYFlowTestCase):
	"""The desk's POS Closing Entry form fills its invoices with the whitelisted ERPNext
	`get_pos_invoices`; it must get the same list as the URY POS."""

	GET_POS_INVOICES = "erpnext.accounts.doctype.pos_closing_entry.pos_closing_entry.get_pos_invoices"

	def test_the_desk_form_calls_the_urys_function(self):
		overrides = frappe.get_hooks("override_whitelisted_methods")
		self.assertEqual(overrides[self.GET_POS_INVOICES][-1], "ury.ury.api.pos_closing.get_pos_invoices")

		open_pos(CASHIER)
		own = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])
		by_captain = place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLES[1])
		pay_order(own)
		pay_order(by_captain)

		method = frappe.get_attr(frappe.get_hooks("override_whitelisted_methods")[self.GET_POS_INVOICES][-1])
		with as_user(CASHIER):
			invoices = method(
				start="2020-01-01 00:00:00", end=frappe.utils.now(), pos_profile=POS_PROFILE, user=CASHIER
			)
		self.assertEqual({inv.name for inv in invoices}, {own, by_captain})


class TestMultipleCashierClosing(URYFlowTestCase):
	def tearDown(self):
		disable_multiple_cashier()
		super().tearDown()

	def test_the_main_cashiers_closing_consolidates_the_sub_cashiers_invoices_too(self):
		enable_multiple_cashier(main=CASHIER)
		main_opening = open_pos(CASHIER)
		sub_opening = open_pos(CASHIER2)

		own = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])
		subs = place_order(CASHIER2, [(FOOD_ITEM, 2), (ALCOHOL_ITEM, 1)], table=TABLES[1])
		paid_main = pay_order(own, user=CASHIER)
		paid_sub = pay_order(subs, user=CASHIER2)

		sub_closing = close_sub_shift(sub_opening)
		# a sub closing does not consolidate anything itself
		self.assertEqual(frappe.db.count("POS Invoice Merge Log"), 0)

		closing = close_shift(main_opening)

		self.assertEqual({row.pos_invoice for row in closing.pos_transactions}, {own, subs})
		logs = merge_logs(closing)
		self.assertEqual(len(logs), 1)
		sales_invoice = frappe.get_doc("Sales Invoice", logs[0].consolidated_invoice)
		self.assertEqual(sales_invoice.grand_total, paid_main.grand_total + paid_sub.grand_total)

		# Known issue (docs/design/pos-closing.md): the main cashier's own counted amount
		# is not added. calculate_closing_amount reads `custom_closing_amount`, which the
		# POS never sends, so the closing amount is the sub closing's alone and the
		# difference is the main cashier's takings (a shortage).
		cash = next(row for row in closing.payment_reconciliation if row.mode_of_payment == "Cash")
		self.assertEqual(cash.closing_amount, sub_closing.payment_reconciliation[0].closing_amount)
		self.assertEqual(cash.difference, -paid_main.grand_total)


class TestSubCashierOpenOrders(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		enable_multiple_cashier(main=CASHIER)
		self.addCleanup(disable_multiple_cashier)
		open_pos(CASHIER)
		self.sub_opening = open_pos(CASHIER2)

	def test_an_open_order_of_the_sub_cashier_blocks_the_closing(self):
		order = place_order(CASHIER2, [(FOOD_ITEM, 1)], table=TABLES[1])
		with self.assertRaises(frappe.ValidationError) as ctx:
			close_sub_shift(self.sub_opening)
		self.assertIn(order, str(ctx.exception))

	def test_a_billed_but_unpaid_order_also_blocks(self):
		order = place_order(CASHIER2, [(FOOD_ITEM, 1)], table=TABLES[1])
		print_bill(order)
		with self.assertRaises(frappe.ValidationError):
			close_sub_shift(self.sub_opening)

	def test_an_order_without_cashier_created_by_the_sub_cashier_blocks(self):
		order = place_order(CASHIER2, [(FOOD_ITEM, 1)], table=TABLES[1])
		frappe.db.set_value("POS Invoice", order, "cashier", None)
		with self.assertRaises(frappe.ValidationError):
			close_sub_shift(self.sub_opening)

	def test_the_sub_cashier_can_close_once_the_order_is_paid(self):
		order = place_order(CASHIER2, [(FOOD_ITEM, 1)], table=TABLES[1])
		pay_order(order, user=CASHIER2)
		self.assertEqual(close_sub_shift(self.sub_opening).docstatus, 1)

	def test_open_orders_of_the_other_cashier_do_not_block(self):
		place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])
		order = place_order(CASHIER2, [(FOOD_ITEM, 1)], table=TABLES[1])
		pay_order(order, user=CASHIER2)
		self.assertEqual(close_sub_shift(self.sub_opening).docstatus, 1)
		# the main cashier's closing is the last safeguard
		self.assertEqual(frappe.db.count("POS Invoice", {"docstatus": 0}), 1)
