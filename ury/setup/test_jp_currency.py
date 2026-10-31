import frappe
from erpnext.controllers.taxes_and_totals import calculate_taxes_and_totals
from frappe.tests.utils import FrappeTestCase
from frappe.utils import fmt_money

from ury.setup.jp_currency import NUMBER_FORMAT, apply_jpy_format, is_jpy_site

COMPANY = "三友寿司"


class TestJPYFormat(FrappeTestCase):
	"""Runs against the dev site inside a transaction that is rolled back."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not is_jpy_site():
			raise cls.skipTest(cls, "needs a Japanese company with JPY")
		cls.result = apply_jpy_format()

	@classmethod
	def tearDownClass(cls):
		super().tearDownClass()
		frappe.db.rollback()
		# defaults and meta were cached while the transaction was open
		frappe.clear_cache()

	def test_number_format_is_whole_yen(self):
		self.assertEqual(frappe.db.get_default("number_format"), NUMBER_FORMAT)
		self.assertEqual(frappe.db.get_value("Currency", "JPY", "number_format"), NUMBER_FORMAT)

	def test_currency_fields_have_precision_zero(self):
		for doctype, fieldname in (
			("Sales Taxes and Charges", "tax_amount"),
			("POS Invoice", "grand_total"),
			("POS Invoice", "rounded_total"),
			("POS Invoice Item", "net_amount"),
		):
			self.assertEqual(frappe.get_precision(doctype, fieldname), 0, f"{doctype}.{fieldname}")

	def test_other_settings_are_left_alone(self):
		self.assertFalse(frappe.db.get_single_value("System Settings", "use_number_format_from_currency"))
		self.assertFalse(frappe.db.get_single_value("System Settings", "currency_precision"))

	def test_fmt_money_has_no_decimals(self):
		for amount in (1234567.5, 53.28, 0, "8.57"):
			self.assertNotIn(".", fmt_money(amount, currency="JPY"), amount)

	def test_daily_pnl_print_has_no_decimals(self):
		doc = frappe.new_doc("URY Daily P and L")
		doc.gross_sales = 1234567.5
		doc.net_sales = 171.43
		html = doc.get_proft_loss_details()
		self.assertIn("1,234,568", html)
		self.assertNotIn("1,234,567.50", html)
		self.assertNotIn("171.43", html)

	def test_taxes_and_totals_are_whole_yen(self):
		"""J3: ERPNext's default tax on 333 + 333 at 8% was 53.28 (grand total 719.28)."""
		template = frappe.db.get_value("Item Tax Template", {"title": "軽減8%", "company": COMPANY})
		if not template:
			self.skipTest("needs the T2 tax structure")
		doc = frappe.new_doc("POS Invoice")
		doc.update(
			{
				"company": COMPANY,
				"currency": "JPY",
				"customer": frappe.db.get_value("Customer", {}, "name"),
				"conversion_rate": 1,
				"plc_conversion_rate": 1,
				"price_list_currency": "JPY",
				"taxes_and_charges": frappe.db.get_value("Sales Taxes and Charges Template", {"title": "消費税（日本）"}),
			}
		)
		doc.append_taxes_from_master()
		for item in ("Burger", "Wings"):
			doc.append(
				"items",
				{"item_code": item, "item_name": item, "qty": 1, "rate": 333, "price_list_rate": 333,
				 "conversion_factor": 1, "item_tax_template": template},
			)
		calculate_taxes_and_totals(doc)

		self.assertEqual([t.tax_amount for t in doc.taxes], [0, 53, 0])
		self.assertEqual(doc.grand_total, 719)
		self.assertEqual(doc.rounded_total, 719)
		self.assertEqual(doc.rounding_adjustment, 0)

	def test_running_twice_changes_nothing(self):
		self.assertEqual(apply_jpy_format(), {"applied": True, "changed": []})
