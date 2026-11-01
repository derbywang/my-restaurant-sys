import frappe

from ury.setup.test_site import (
	ABBR,
	ALCOHOL_ITEM,
	CASHIER,
	CASHIER2,
	COMPANY,
	CUSTOMER,
	CUSTOMER2,
	FOOD_ITEM,
	POS_PROFILE,
	PRICE_LIST,
	RESTAURANT,
	TABLES,
	URYFlowTestCase,
	URYTestCase,
	close_shift,
	open_pos,
	pay_order,
	place_order,
)
from ury.overrides.pos_invoice import URYPOSInvoice, URYTaxesAndTotals
from ury.ury.hooks.ury_pos_invoice import set_tax_category


def calculate(order_type, rows, rounding=None, **extra):
	"""What happens on save, nothing is saved. rows: [(item, rate, qty)]."""
	if rounding:
		frappe.db.set_value("POS Profile", POS_PROFILE, "custom_tax_rounding", rounding)
		frappe.clear_cache(doctype="POS Profile")
	doc = frappe.new_doc("POS Invoice")
	doc.update(
		{
			"company": COMPANY,
			"currency": "JPY",
			"customer": frappe.db.get_value("Customer", {}, "name"),
			"conversion_rate": 1,
			"plc_conversion_rate": 1,
			"price_list_currency": "JPY",
			"selling_price_list": PRICE_LIST,
			"posting_date": "2026-11-01",
			"taxes_and_charges": frappe.db.get_value("Sales Taxes and Charges Template", {"title": "消費税（日本）"}),
			"order_type": order_type,
			"restaurant": RESTAURANT,
			"pos_profile": POS_PROFILE,
			**extra,
		}
	)
	doc.append_taxes_from_master()
	for item, rate, qty in rows:
		doc.append(
			"items",
			{"item_code": item, "item_name": item, "qty": qty, "rate": rate, "price_list_rate": rate, "conversion_factor": 1},
		)
	set_tax_category(doc, "before_validate")
	doc.set_missing_item_details(for_validate=True)
	doc.calculate_taxes_and_totals()
	return doc


def taxes(doc):
	return [t.tax_amount for t in doc.taxes]


class TestTaxRounding(URYTestCase):
	@classmethod
	def tearDownClass(cls):
		super().tearDownClass()
		frappe.db.rollback()
		frappe.clear_cache()

	def test_the_pos_invoice_uses_the_override(self):
		self.assertIsInstance(frappe.new_doc("POS Invoice"), URYPOSInvoice)

	def test_j3_two_rows_of_333_are_taxed_once(self):
		doc = calculate("Take Away", [(FOOD_ITEM, 333, 1), (FOOD_ITEM, 333, 1)])
		self.assertEqual(taxes(doc), [0, 53, 0])  # floor(53.28), not per row
		self.assertEqual(doc.grand_total, 719)
		self.assertEqual(doc.rounded_total, 719)

	def test_j3b_333_times_three(self):
		doc = calculate("Take Away", [(FOOD_ITEM, 333, 3)])
		self.assertEqual(taxes(doc), [0, 79, 0])  # floor(79.92)
		self.assertEqual(doc.grand_total, 1078)
		self.assertEqual(doc.rounded_total, 1078)

	def test_items_of_another_rate_are_not_in_the_rate_of_the_row(self):
		"""ERPNext adds every item to `net_amount` of every row (an item the row's rate is 0
		for too), so the tax cannot be taken from the row's net amount."""
		doc = calculate("Take Away", [(FOOD_ITEM, 1000, 1), (ALCOHOL_ITEM, 500, 1)])
		ten_percent, eight_percent, _one = doc.taxes
		self.assertEqual(ten_percent.net_amount, 1500)  # the 8% food is in it
		self.assertEqual(ten_percent.tax_amount, 50)  # but only the beer is taxed: 500 * 10%
		self.assertEqual(eight_percent.net_amount, 1500)
		self.assertEqual(eight_percent.tax_amount, 80)  # 1000 * 8%
		self.assertEqual(doc.grand_total, 1630)

	def test_j1_dine_in_all_ten_percent(self):
		doc = calculate("Dine In", [(FOOD_ITEM, 1000, 1), (ALCOHOL_ITEM, 500, 1)])
		self.assertEqual(taxes(doc), [150, 0, 0])
		self.assertEqual(doc.grand_total, 1650)

	def test_the_rate_is_applied_to_the_total_not_to_each_row(self):
		# per row: 0.1 * 5 = 0.5 -> 0 (banker's) each; together 0.1 * 15 = 1.5
		rows = [(ALCOHOL_ITEM, 5, 1)] * 3
		self.assertEqual(taxes(calculate("Dine In", rows)), [1, 0, 0])

	def test_the_rounding_is_configurable(self):
		rows = [(FOOD_ITEM, 333, 3)]  # 79.92
		cases = {"Round Down": 79, "Round Half Up": 80, "Round Up": 80}
		for mode, expected in cases.items():
			self.assertEqual(calculate("Take Away", rows, rounding=mode).taxes[1].tax_amount, expected, mode)
		rows = [(FOOD_ITEM, 333, 2)]  # 53.28
		cases = {"Round Down": 53, "Round Half Up": 53, "Round Up": 54}
		for mode, expected in cases.items():
			self.assertEqual(calculate("Take Away", rows, rounding=mode).taxes[1].tax_amount, expected, mode)

	def test_an_unset_rounding_means_round_down(self):
		frappe.db.set_value("POS Profile", POS_PROFILE, "custom_tax_rounding", None)
		frappe.clear_cache(doctype="POS Profile")
		self.assertEqual(calculate("Take Away", [(FOOD_ITEM, 333, 3)]).taxes[1].tax_amount, 79)

	def test_the_patch_default_is_round_down(self):
		frappe.db.set_value("POS Profile", POS_PROFILE, "custom_tax_rounding", None)
		from ury.patches.v2_0.tax_rounding import execute

		execute()
		self.assertEqual(frappe.db.get_value("POS Profile", POS_PROFILE, "custom_tax_rounding"), "Round Down")

	# --- J9: a discount on the whole order is taken off the amount without tax ---
	NET_10 = {"additional_discount_percentage": 10}

	def setUp(self):
		super().setUp()
		frappe.db.set_value("POS Profile", POS_PROFILE, "apply_discount_on", "Net Total")
		frappe.clear_document_cache("POS Profile", POS_PROFILE)

	def test_j9_dine_in_discount_of_ten_percent(self):
		doc = calculate("Dine In", [(FOOD_ITEM, 1000, 1), (ALCOHOL_ITEM, 500, 1)], **self.NET_10)
		self.assertEqual(doc.net_total, 1350)
		self.assertEqual(taxes(doc), [135, 0, 0])
		self.assertEqual(doc.grand_total, 1485)
		self.assertEqual(doc.rounded_total, 1485)

	def test_j9_take_away_mixed_rates_each_rate_once(self):
		doc = calculate("Take Away", [(FOOD_ITEM, 1000, 1), (ALCOHOL_ITEM, 500, 1)], **self.NET_10)
		self.assertEqual(doc.net_total, 1350)
		self.assertEqual(taxes(doc), [45, 72, 0])  # 450 * 10%, 900 * 8%
		self.assertEqual(doc.grand_total, 1467)

	def test_j9_tail_amounts_with_a_discount(self):
		rows = [(FOOD_ITEM, 333, 3), (FOOD_ITEM, 111, 1), (ALCOHOL_ITEM, 333, 3), (ALCOHOL_ITEM, 77, 1)]
		for percent in (10, 15, 33):
			doc = calculate("Take Away", rows, additional_discount_percentage=percent)
			ten, eight, _one = doc.taxes
			foods = sum(i.net_amount for i in doc.items if i.item_code == FOOD_ITEM)
			beers = sum(i.net_amount for i in doc.items if i.item_code == ALCOHOL_ITEM)
			self.assertEqual(eight.tax_amount, int(foods * 8 // 100), percent)  # floored, once
			self.assertEqual(ten.tax_amount, int(beers * 10 // 100), percent)
			self.assertEqual(eight.tax_amount_after_discount_amount, eight.tax_amount)
			self.assertEqual(doc.grand_total, doc.net_total + ten.tax_amount + eight.tax_amount)
			self.assertEqual(doc.rounded_total, doc.grand_total)

	def test_a_discount_on_the_grand_total_is_refused_in_japan(self):
		"""The POS Profile decides, so the profile has to be set wrong for this."""
		frappe.db.set_value("POS Profile", POS_PROFILE, "apply_discount_on", "Grand Total")
		frappe.clear_document_cache("POS Profile", POS_PROFILE)
		with self.assertRaises(frappe.ValidationError) as ctx:
			calculate("Dine In", [(FOOD_ITEM, 1000, 1)], additional_discount_percentage=10)
		self.assertIn("Net Total", str(ctx.exception))
		with self.assertRaises(frappe.ValidationError):
			calculate("Dine In", [(FOOD_ITEM, 1000, 1)], discount_amount=100)

	def test_the_invoice_takes_apply_discount_on_from_the_pos_profile(self):
		frappe.db.set_value("POS Profile", POS_PROFILE, "apply_discount_on", "Net Total")
		frappe.clear_document_cache("POS Profile", POS_PROFILE)
		# the field default of a new invoice is Grand Total
		doc = calculate("Dine In", [(FOOD_ITEM, 1000, 1)], additional_discount_percentage=10)
		self.assertEqual(doc.apply_discount_on, "Net Total")
		self.assertEqual(doc.grand_total, 990)

	def test_without_a_discount_the_grand_total_setting_does_no_harm(self):
		frappe.db.set_value("POS Profile", POS_PROFILE, "apply_discount_on", "Grand Total")
		frappe.clear_document_cache("POS Profile", POS_PROFILE)
		doc = calculate("Dine In", [(FOOD_ITEM, 1000, 1)])
		self.assertEqual(doc.grand_total, 1100)

	def test_the_patch_sets_net_total_on_the_japanese_profiles(self):
		from ury.patches.v2_0.jp_discount_on_net_total import execute

		frappe.db.set_value("POS Profile", POS_PROFILE, "apply_discount_on", "Grand Total")
		execute()
		self.assertEqual(frappe.db.get_value("POS Profile", POS_PROFILE, "apply_discount_on"), "Net Total")


class TestTaxesAddUpAfterClosing(URYFlowTestCase):
	"""J7: the Sales Invoices made by the closing have the tax of every rate of the POS invoices."""

	def test_tail_amounts_agree_between_pos_invoices_and_sales_invoices(self):
		prices = frappe.get_all("Item Price", filters={"price_list": PRICE_LIST, "item_code": FOOD_ITEM}, fields=["name", "price_list_rate"])
		self.addCleanup(self._restore, prices)
		for price in prices:
			frappe.db.set_value("Item Price", price.name, "price_list_rate", 333)
		frappe.db.commit()
		frappe.clear_cache()

		opening = open_pos(CASHIER)
		orders = [
			place_order(CASHIER, [(FOOD_ITEM, 2)], table=TABLES[0], order_type="Take Away", customer=CUSTOMER),
			place_order(CASHIER, [(FOOD_ITEM, 3)], table=TABLES[1], order_type="Take Away", customer=CUSTOMER),
			place_order(CASHIER, [(FOOD_ITEM, 3)], table=TABLES[2], customer=CUSTOMER2),
		]
		paid = [pay_order(name) for name in orders]
		self.assertEqual([p.taxes[1].tax_amount for p in paid[:2]], [53, 79])
		self.assertEqual(paid[2].taxes[0].tax_amount, 99)  # floor(99.9), dine in

		closing = close_shift(opening)

		sales_invoices = [
			frappe.get_doc("Sales Invoice", log.consolidated_invoice)
			for log in frappe.get_all("POS Invoice Merge Log", filters={"pos_closing_entry": closing.name}, fields=["consolidated_invoice"])
		]
		self.assertEqual(len(sales_invoices), 2)

		def by_account(docs):
			total = {}
			for doc in docs:
				for row in doc.taxes:
					total[row.account_head] = total.get(row.account_head, 0) + row.tax_amount
			return {account: amount for account, amount in total.items() if amount}

		self.assertEqual(by_account(sales_invoices), by_account(paid))
		self.assertEqual(sum(si.grand_total for si in sales_invoices), sum(p.grand_total for p in paid))
		for sales_invoice in sales_invoices:
			self.assertEqual(sales_invoice.outstanding_amount, 0)

	def test_discounted_orders_add_up_after_closing(self):
		original = frappe.db.get_value("POS Profile", POS_PROFILE, ["apply_discount_on", "custom_enable_discount"])
		self.addCleanup(self._set_discount_on, *original)
		self._set_discount_on("Net Total", 1)

		opening = open_pos(CASHIER)
		orders = [
			place_order(CASHIER, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)], table=TABLES[0], customer=CUSTOMER),
			place_order(CASHIER, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)], table=TABLES[1], order_type="Take Away", customer=CUSTOMER),
		]
		paid = [pay_order(name, discount=10) for name in orders]
		self.assertEqual([p.net_total for p in paid], [1350, 1350])
		self.assertEqual([p.grand_total for p in paid], [1485, 1467])

		closing = close_shift(opening)

		logs = frappe.get_all("POS Invoice Merge Log", filters={"pos_closing_entry": closing.name}, fields=["consolidated_invoice"])
		self.assertEqual(len(logs), 1)
		sales_invoice = frappe.get_doc("Sales Invoice", logs[0].consolidated_invoice)
		self.assertEqual(sales_invoice.grand_total, 1485 + 1467)
		self.assertEqual({r.account_head: r.tax_amount for r in sales_invoice.taxes if r.tax_amount},
			{f"CT 10% - {ABBR}": 135 + 45, f"CT 8% - {ABBR}": 72})

	def _set_discount_on(self, value, enabled):
		frappe.db.set_value("POS Profile", POS_PROFILE, {"apply_discount_on": value, "custom_enable_discount": enabled})
		frappe.db.commit()
		frappe.clear_document_cache("POS Profile", POS_PROFILE)
		frappe.clear_cache(doctype="POS Profile")

	def _restore(self, prices):
		for price in prices:
			frappe.db.set_value("Item Price", price.name, "price_list_rate", price.price_list_rate)
		frappe.db.commit()
		frappe.clear_cache()
