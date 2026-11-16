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
