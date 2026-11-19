"""The receipt printer and the drawer, from the POS (ury/ury/api/receipt_print.py), against fake printers.

The printer's settings (DocType URY Receipt Printer) and the drawer log come with the migrate of 2026-11; here the
three seams that read and write them are replaced: `printer_config_for`, `write_log`, `RENDERER`. Read-only on the
site except for the orders the tests place and the transaction rolls back. Run on the test site only.
"""

from unittest.mock import patch

import frappe

from ury.printing import service
from ury.printing.test_printing_core import FakeEpos, FakeRaw
from ury.ury.api import receipt_print as rp
from ury.ury.api.test_captain_access import CAPTAIN_B, make_captain, remove_captain
from ury.setup.test_site import (
	CAPTAIN,
	CASHIER,
	FOOD_ITEM,
	TABLES,
	URYFlowTestCase,
	as_user,
	open_pos,
	pay_order,
	pay_with,
	place_order,
)
from ury.ury.api.test_receipt import text
from ury.ury.api.test_receipt_payment import CREDIT_NOTE, MIXED_NOTE, STAMP_BOX

BITS = (b"\xff" * 72) * 10, 72, 10


def fake_renderer(html, paper_mm):
	fake_renderer.calls.append(html)
	return BITS


fake_renderer.calls = []


class PrinterTestCase(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		fake_renderer.calls.clear()
		self.printer = FakeEpos()
		self.addCleanup(self.printer.server_close)
		self.addCleanup(self.printer.shutdown)
		self.config = service.PrinterConfig(address="127.0.0.1", protocol="epos", port=self.printer.port)
		self.logs = []
		for target, value in (
			(rp, {"RENDERER": fake_renderer}),
		):
			for name, new in value.items():
				p = patch.object(target, name, new)
				p.start()
				self.addCleanup(p.stop)
		p = patch.object(rp, "printer_config_for", lambda branch: self.config)
		p.start()
		self.addCleanup(p.stop)
		p = patch.object(rp, "write_log", lambda **fields: self.logs.append(fields))
		p.start()
		self.addCleanup(p.stop)
		self.opening = open_pos(CASHIER)

	def pulses(self):
		return sum("<pulse" in body for _, _, body in self.printer.received)

	def images(self):
		return sum("<image" in body for _, _, body in self.printer.received)


class TestPrintBill(PrinterTestCase):
	def test_a_waiter_prints_the_bill_without_the_drawer(self):
		invoice = place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLES[0])
		with as_user(CAPTAIN):
			result = rp.print_bill(invoice)
		self.assertTrue(result["ok"], result)
		self.assertEqual(self.images(), 1)
		self.assertEqual(self.pulses(), 0)
		self.assertEqual(len(fake_renderer.calls), 1)

	def test_no_printer_is_a_message_not_an_error(self):
		invoice = place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLES[0])
		with patch.object(rp, "printer_config_for", lambda branch: None), as_user(CAPTAIN):
			result = rp.print_bill(invoice)
		self.assertFalse(result["ok"])
		self.assertIn("プリンター", result["message"])

	def test_a_printer_trouble_is_a_message(self):
		invoice = place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLES[0])
		self.config = service.PrinterConfig(address="127.0.0.1", protocol="epos", port=9, timeout=1)
		with as_user(CAPTAIN):
			result = rp.print_bill(invoice)
		self.assertFalse(result["ok"])
		self.assertIn("接続できません", result["message"])

	def test_a_waiter_cannot_print_what_she_cannot_see(self):
		paid = pay_order(place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLES[1]))
		with as_user(CAPTAIN):
			with self.assertRaises(frappe.PermissionError):
				rp.print_bill(paid.name)
		self.assertEqual(self.printer.received, [])

	def test_the_cashier_reprints_a_receipt_without_opening_the_drawer(self):
		paid = pay_order(place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[1]))
		with as_user(CASHIER):
			result = rp.print_bill(paid.name)
		self.assertTrue(result["ok"], result)
		self.assertEqual(self.pulses(), 0)


class TestOpenDrawer(PrinterTestCase):
	def test_the_cashier_opens_it_and_it_is_logged(self):
		with as_user(CASHIER):
			result = rp.open_drawer()
		self.assertTrue(result["ok"], result)
		self.assertEqual((self.pulses(), self.images()), (1, 0))
		self.assertEqual(len(self.logs), 1)
		self.assertEqual((self.logs[0]["user"], self.logs[0]["reason"], self.logs[0]["ok"]), (CASHIER, "manual", True))

	def test_a_waiter_cannot_and_nothing_is_sent(self):
		with as_user(CAPTAIN):
			with self.assertRaises(frappe.PermissionError):
				rp.open_drawer()
		self.assertEqual((self.printer.received, self.logs), ([], []))

	def test_a_drawer_that_does_not_open_is_logged_as_failed(self):
		self.config = service.PrinterConfig(address="127.0.0.1", protocol="epos", port=9, timeout=1)
		with as_user(CASHIER):
			result = rp.open_drawer()
		self.assertFalse(result["ok"])
		self.assertIn("鍵", result["message"])
		self.assertFalse(self.logs[0]["ok"])

	def test_no_printer_is_a_message_and_a_log(self):
		with patch.object(rp, "printer_config_for", lambda branch: None), as_user(CASHIER):
			result = rp.open_drawer()
		self.assertFalse(result["ok"])
		self.assertEqual(len(self.logs), 1)


class TestDrawerAtSettlement(PrinterTestCase):
	def order(self, table=0):
		return place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[table])

	def test_a_cash_sale_opens_the_drawer_and_is_logged(self):
		paid = pay_with(self.order(), [("Cash", 1100)])
		with as_user(CASHIER):
			result = rp.drawer_for_settlement(paid.name)
		self.assertTrue(result["ok"], result)
		self.assertTrue(result["opened"])
		self.assertEqual((self.pulses(), self.images()), (1, 0))
		self.assertEqual((self.logs[0]["reason"], self.logs[0]["invoice"]), ("settlement", paid.name))

	def test_change_given_opens_the_drawer(self):
		paid = pay_with(self.order(), [("Cash", 1500)])
		with as_user(CASHIER):
			result = rp.drawer_for_settlement(paid.name)
		self.assertTrue(result["opened"])

	def test_a_printer_without_a_drawer_is_not_a_failure_at_settlement(self):
		# the shop has no drawer on this printer (yet): cash is taken and there is nothing to open, so no red message after the payment
		self.config = service.PrinterConfig(address="127.0.0.1", protocol="epos", port=self.printer.port, has_drawer=False)
		paid = pay_with(self.order(), [("Cash", 1100)])
		with as_user(CASHIER):
			result = rp.drawer_for_settlement(paid.name)
		self.assertEqual((result["ok"], result["opened"], result["message"]), (True, False, ""))
		self.assertEqual(self.printer.received, [])

	def test_the_button_still_says_so_when_the_printer_has_no_drawer(self):
		self.config = service.PrinterConfig(address="127.0.0.1", protocol="epos", port=self.printer.port, has_drawer=False)
		with as_user(CASHIER):
			result = rp.open_drawer()
		self.assertFalse(result["ok"])
		self.assertIn("引き出し", result["message"])

	def test_an_open_order_is_refused(self):
		with as_user(CASHIER):
			with self.assertRaises(frappe.ValidationError):
				rp.drawer_for_settlement(self.order())
		self.assertEqual(self.printer.received, [])

	def test_a_waiter_cannot(self):
		paid = pay_with(self.order(), [("Cash", 1100)])
		with as_user(CAPTAIN):
			with self.assertRaises(frappe.PermissionError):
				rp.drawer_for_settlement(paid.name)

	def test_a_failure_is_a_message_and_never_an_error(self):
		paid = pay_with(self.order(), [("Cash", 1100)])
		self.config = service.PrinterConfig(address="127.0.0.1", protocol="epos", port=9, timeout=1)
		with as_user(CASHIER):
			result = rp.drawer_for_settlement(paid.name)
		self.assertFalse(result["ok"])
		self.assertFalse(result["opened"])
		self.assertIn("鍵", result["message"])

	def test_over_port_9100_too(self):
		raw = FakeRaw()
		self.config = service.PrinterConfig(address="127.0.0.1", protocol="escpos", port=raw.port)
		paid = pay_with(self.order(), [("Cash", 1100)])
		with as_user(CASHIER):
			result = rp.drawer_for_settlement(paid.name)
		raw.thread.join(3)
		self.assertTrue(result["ok"], result)
		self.assertIn(b"\x1bp", raw.job)


class TestWhatCountsAsCash(PrinterTestCase):
	def test_cash_rows_and_change(self):
		cash = {"Cash"}
		self.assertEqual(rp.cash_and_change([("Cash", 1100)], 0, cash), (1100, 0))
		self.assertEqual(rp.cash_and_change([("Cash", 1500)], 400, cash), (1500, 400))
		self.assertEqual(rp.cash_and_change([("Card", 1100)], 0, cash), (0, 0))
		self.assertEqual(rp.cash_and_change([("Card", 600), ("Cash", 500)], 0, cash), (500, 0))
		self.assertEqual(rp.cash_and_change([], None, cash), (0, 0))


class TestWhichWayToPrint(PrinterTestCase):
	def test_a_chosen_server_printer_wins_over_the_old_ways(self):
		self.assertEqual(rp.print_type_for(server_printer="レジ", qz_print=1, bill_printer_present=True), "server")

	def test_without_it_the_old_rules_stay(self):
		self.assertEqual(rp.print_type_for(server_printer=None, qz_print=1, bill_printer_present=False), "qz")
		self.assertEqual(rp.print_type_for(server_printer="", qz_print=0, bill_printer_present=True), "network")
		self.assertEqual(rp.print_type_for(server_printer=None, qz_print=0, bill_printer_present=False), "socket")


class TestTheReceiptTheButtonAfterAPaymentPrints(PrinterTestCase):
	"""2026-11-20: after a payment the cashier is offered 「領収書を印刷」; the button prints through `print_bill` of the paid invoice
	(the drawer stays shut). What it prints is the receipt as before for every way of paying and for a merged or split bill: the
	method line, the card notes, the 収入印紙 貼付欄 when the cash kept is 50,000 yen or more without the tax."""

	def setUp(self):
		super().setUp()
		original = frappe.db.get_value("Item Price", {"item_code": FOOD_ITEM, "selling": 1}, "price_list_rate")
		self.addCleanup(self._set_price, original)

	def _set_price(self, price):
		frappe.db.sql("update `tabItem Price` set price_list_rate = %s where item_code = %s and selling = 1", (price, FOOD_ITEM))
		frappe.db.commit()

	def _receipt(self, invoice):
		with as_user(CASHIER):
			result = rp.print_bill(invoice)
		self.assertTrue(result["ok"], result)
		self.assertEqual(self.pulses(), 0)  # the drawer stays shut
		return text(fake_renderer.calls[-1])

	def _paid(self, price, payments, table=0):
		self._set_price(price)
		order = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[table])
		pay_with(order, payments)
		return order

	def test_cash_of_fifty_thousand_without_the_tax_has_the_place_for_a_stamp(self):
		out = self._receipt(self._paid(50000, [("Cash", 55000)]))
		self.assertIn("お支払方法：現金", out)
		self.assertIn(STAMP_BOX, out)

	def test_cash_below_it_has_none(self):
		self.assertNotIn(STAMP_BOX, self._receipt(self._paid(49999, [("Cash", 54998)])))

	def test_the_change_is_taken_off_the_cash(self):
		self.assertNotIn(STAMP_BOX, self._receipt(self._paid(40000, [("Cash", 60000)])))

	def test_a_card_says_the_credit_note_and_never_a_stamp(self):
		out = self._receipt(self._paid(100000, [("クレジットカード", 110000)]))
		self.assertIn(CREDIT_NOTE, out)
		self.assertNotIn(STAMP_BOX, out)

	def test_cash_and_card_print_each_amount_with_the_note_for_the_card_part(self):
		out = self._receipt(self._paid(100000, [("Cash", 55000), ("クレジットカード", 55000)]))
		self.assertIn("クレジットカード | ¥55,000", out)
		self.assertIn("お預かり（現金） | ¥55,000", out)
		self.assertIn(MIXED_NOTE, out)
		self.assertIn(STAMP_BOX, out)  # 55,000 of 110,000 kept in cash is 50,000 without the tax

	def test_a_wallet_prints_its_name_and_nothing_of_the_stamp(self):
		out = self._receipt(self._paid(100000, [("PayPay", 110000)]))
		self.assertIn("お支払方法：PayPay", out)
		self.assertNotIn("印紙", out)

	def test_a_merged_bill_prints_both_bills_and_the_total_it_was_paid_for(self):
		from frappe.utils import add_to_date

		from ury.ury_pos.api import merge_bills

		self._set_price(1000)
		first = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])
		second = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[1])
		made = frappe.db.get_value("POS Invoice", first, "creation")
		frappe.db.set_value("POS Invoice", second, "creation", add_to_date(made, seconds=1), update_modified=False)
		with as_user(CASHIER):
			merge_bills(first, second)
		pay_with(first, [("Cash", 2300)], expected_total=2200)
		out = self._receipt(first)
		self.assertIn(first, out)
		self.assertIn(second, out)
		self.assertIn("合計（税込） | ¥2,200", out)
		self.assertIn("お釣り | ¥100", out)

	def test_a_part_of_a_split_bill_prints_its_own_dishes_and_total(self):
		from ury.ury.doctype.ury_order.ury_order import split_bill

		self._set_price(1000)
		order = place_order(CASHIER, [(FOOD_ITEM, 2)], table=TABLES[0])
		row = frappe.get_all("POS Invoice Item", filters={"parent": order}, pluck="name")[0]
		with as_user(CASHIER):
			split = split_bill(order, [{"name": row, "qty": 1}])["new_invoice"]
		frappe.db.commit()
		pay_with(split, [("Cash", 1100)])
		out = self._receipt(split)
		self.assertIn("合計（税込） | ¥1,100", out)
		self.assertIn("1 × ¥1,000", out)
