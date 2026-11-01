"""The Japanese receipt (docs/design/jp-tax-design.md 4.6, J1-J3, J6, J9, J10) and the three
ways to print it. Run on the test site only (see docs/testing/test-site.md)."""

from unittest import mock

import frappe

from ury.setup.jp_tax import RECEIPT_FORMAT, apply_receipt_format, refresh_receipt_format
from ury.setup.test_site import (
	ALCOHOL_ITEM,
	CAPTAIN,
	CASHIER,
	COMPANY,
	FOOD_ITEM,
	POS_PROFILE,
	TABLES,
	URYFlowTestCase,
	as_user,
	open_pos,
	pay_order,
	place_order,
)
from ury.ury.api.receipt import is_registration_number


def render(invoice):
	return frappe.get_print("POS Invoice", invoice, RECEIPT_FORMAT, no_letterhead=1)


def text(html):
	"""The visible text of the receipt, one line per table row / block."""
	import re

	html = re.sub(r"<style.*?</style>", "", html, flags=re.S)
	html = re.sub(r"</(tr|div|p)>", "\n", html)
	html = re.sub(r"</t[dh]>", " | ", html)
	return re.sub(r"[ \t]+", " ", re.sub(r"<[^>]+>", "", html))


class TestJPReceipt(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		refresh_receipt_format()
		frappe.db.commit()
		self.original_tax_id = frappe.db.get_value("Company", COMPANY, "tax_id")
		self.addCleanup(self._set_tax_id, self.original_tax_id)
		self._set_tax_id("T1234567890123")
		open_pos(CASHIER)

	def _set_tax_id(self, value):
		frappe.db.set_value("Company", COMPANY, "tax_id", value)
		frappe.db.commit()
		frappe.clear_document_cache("Company", COMPANY)

	def test_dine_in_bill_before_payment(self):
		order = place_order(CASHIER, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)], table=TABLES[0])
		out = text(render(order))
		self.assertIn("ご請求明細", out)
		self.assertNotIn("領収書", out)
		self.assertIn("登録番号 T1234567890123", out)
		self.assertIn("店内", out)
		self.assertIn("10%対象（税抜） | ¥1,500", out)
		self.assertIn("消費税等 10% | ¥150", out)
		self.assertIn("合計（税込） | ¥1,650", out)
		self.assertNotIn("お預かり", out)
		self.assertNotIn("※", out)

	def test_take_away_receipt_marks_the_reduced_rate(self):
		order = place_order(CASHIER, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)], table=TABLES[0], order_type="Take Away")
		pay_order(order)
		out = text(render(order))
		self.assertIn("領収書", out)
		self.assertIn("お持ち帰り", out)
		self.assertIn(f"※{FOOD_ITEM}", out)
		self.assertNotIn(f"※{ALCOHOL_ITEM}", out)
		self.assertIn("※8%対象（税抜） | ¥1,000", out)
		self.assertIn("消費税等 8% | ¥80", out)
		self.assertIn("10%対象（税抜） | ¥500", out)
		self.assertIn("消費税等 10% | ¥50", out)
		self.assertIn("合計（税込） | ¥1,630", out)
		self.assertIn("お預かり | ¥1,630", out)
		self.assertIn("※は軽減税率対象", out)

	def test_a_discount_is_shown_and_the_rates_follow_it(self):
		order = place_order(CASHIER, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)], table=TABLES[0])
		self._enable_discount()
		pay_order(order, discount=10)
		out = text(render(order))
		self.assertIn("割引 | -¥150", out)
		self.assertIn("10%対象（税抜） | ¥1,350", out)
		self.assertIn("消費税等 10% | ¥135", out)
		self.assertIn("合計（税込） | ¥1,485", out)

	def test_a_tail_amount_is_rounded_down(self):
		original = frappe.db.get_value("Item Price", {"item_code": FOOD_ITEM, "selling": 1}, "price_list_rate")
		frappe.db.sql("update `tabItem Price` set price_list_rate = 333 where item_code = %s and selling = 1", FOOD_ITEM)
		frappe.db.commit()
		self.addCleanup(self._restore_price, original)
		order = place_order(CASHIER, [(FOOD_ITEM, 3)], table=TABLES[0], order_type="Take Away")
		out = text(render(order))
		self.assertIn("8%対象（税抜） | ¥999", out)
		self.assertIn("消費税等 8% | ¥79", out)
		self.assertIn("合計（税込） | ¥1,078", out)

	def test_a_merged_bill_adds_the_rates_of_both_invoices(self):
		from ury.ury_pos.api import merge_bills

		first = place_order(CASHIER, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)], table=TABLES[0])
		second = place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLES[1], order_type="Take Away")
		with as_user(CASHIER):
			merge_bills(first, second)
		out = text(render(first))
		self.assertIn(first, out)
		self.assertIn(second, out)
		# 1,500 at 10% (dine-in) + 1,000 at 8% (take-away)
		self.assertIn("10%対象（税抜） | ¥1,500", out)
		self.assertIn("消費税等 10% | ¥150", out)
		self.assertIn("※8%対象（税抜） | ¥1,000", out)
		self.assertIn("消費税等 8% | ¥80", out)
		self.assertIn("合計（税込） | ¥2,730", out)

	def test_a_missing_or_wrong_registration_number_still_prints(self):
		order = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])
		for value in (None, "", "1234567890123", "T123"):
			self._set_tax_id(value)
			out = text(render(order))
			self.assertIn("登録番号 未設定", out)
			self.assertIn("合計（税込） | ¥1,100", out)
		self.assertTrue(is_registration_number("T1234567890123"))
		self.assertFalse(is_registration_number("T12345678901234"))

	def test_saved_amounts_are_printed_when_a_new_calculation_differs(self):
		order = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])
		row = frappe.db.get_value("Sales Taxes and Charges", {"parent": order, "tax_amount": [">", 0]}, "name")
		frappe.db.set_value("Sales Taxes and Charges", row, "tax_amount_after_discount_amount", 101)
		before = frappe.db.count("Error Log", {"method": ["like", "Receipt:%"]})
		out = text(render(order))
		self.assertIn("消費税等 10% | ¥101", out)  # the saved amount
		self.assertEqual(frappe.db.count("Error Log", {"method": ["like", "Receipt:%"]}), before + 1)

	def test_no_error_log_when_everything_agrees(self):
		order = place_order(CASHIER, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 2)], table=TABLES[0], order_type="Take Away")
		before = frappe.db.count("Error Log", {"method": ["like", "Receipt:%"]})
		render(order)
		self.assertEqual(frappe.db.count("Error Log", {"method": ["like", "Receipt:%"]}), before)

	# --- the three ways to print -------------------------------------------------

	def test_the_pos_profile_uses_the_receipt_format(self):
		changed = apply_receipt_format()
		self.assertEqual(frappe.db.get_value("POS Profile", POS_PROFILE, "print_format"), RECEIPT_FORMAT)
		self.assertNotIn(POS_PROFILE, apply_receipt_format()["changed"])  # idempotent
		self.assertIsInstance(changed["changed"], list)

	def test_qz_tray_gets_the_receipt_html(self):
		"""QZ Tray: the POS fetches the HTML with frappe.www.printview.get_html_and_style."""
		from frappe.www.printview import get_html_and_style

		order = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])
		with as_user(CASHIER):
			html = get_html_and_style(
				doc="POS Invoice", name=order, print_format=RECEIPT_FORMAT, no_letterhead=1
			)["html"]
		self.assertIn("ご請求明細", html)
		self.assertIn("合計（税込）", html)

	def test_network_printing_uses_the_receipt_format(self):
		"""Network printer: `select_network_printer` takes the format of the POS Profile (or the
		one the POS sends) and hands it to `network_printing`, which renders it with
		frappe.get_print (the PDF itself needs wkhtmltopdf and a CUPS server, so it is not made here)."""
		from ury.ury.api import ury_print

		order = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])
		apply_receipt_format()
		with as_user(CASHIER), mock.patch.object(ury_print.frappe, "get_all", return_value=["printer"]):
			with mock.patch.object(ury_print, "network_printing") as network:
				ury_print.select_network_printer(POS_PROFILE, order)
				self.assertEqual(network.call_args.args[3], RECEIPT_FORMAT)
				ury_print.select_network_printer(POS_PROFILE, order, print_format="Other Format")
				self.assertEqual(network.call_args.args[3], "Other Format")

	def test_websocket_printing_sends_the_receipt_format(self):
		"""Websocket print: the POS Invoice page publishes the format name; the print page
		renders it with get_html_and_style (as QZ above)."""
		from ury.ury.api.ury_print import print_pos_page

		order = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])
		with as_user(CASHIER), mock.patch("frappe.publish_realtime") as publish:
			print_pos_page("POS Invoice", order, RECEIPT_FORMAT)
		self.assertEqual(publish.call_args.args[1]["data"]["print_format"], RECEIPT_FORMAT)

	def _enable_discount(self):
		original = frappe.db.get_value("POS Profile", POS_PROFILE, ["apply_discount_on", "custom_enable_discount"])
		frappe.db.set_value("POS Profile", POS_PROFILE, {"apply_discount_on": "Net Total", "custom_enable_discount": 1})
		frappe.db.commit()
		frappe.clear_document_cache("POS Profile", POS_PROFILE)
		self.addCleanup(self._restore_discount, *original)

	def _restore_discount(self, apply_on, enabled):
		frappe.db.set_value("POS Profile", POS_PROFILE, {"apply_discount_on": apply_on, "custom_enable_discount": enabled})
		frappe.db.commit()
		frappe.clear_document_cache("POS Profile", POS_PROFILE)

	def _restore_price(self, original):
		frappe.db.sql(
			"update `tabItem Price` set price_list_rate = %s where item_code = %s and selling = 1", (original, FOOD_ITEM)
		)
		frappe.db.commit()
