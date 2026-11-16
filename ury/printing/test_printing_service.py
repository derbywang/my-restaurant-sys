"""What the server does with a printer's settings (ury/printing/service.py), against fake printers. No site, no database.

Run:  cd apps/ury && ../../env/bin/python -W ignore -m unittest ury.printing.test_printing_service
"""

import unittest

from ury.printing import service
from ury.printing.test_printing_core import FakeEpos, FakeRaw

BITS = (b"\xff" * 72) * 10, 72, 10  # a black band: (bits, width_bytes, height)


def renderer(html, paper_mm):
	renderer.calls.append((html, paper_mm))
	return BITS


renderer.calls = []


def failing_renderer(html, paper_mm):
	from ury.printing.bitmap import RenderError

	raise RenderError("wkhtmltoimage is missing")


class TestDrawerRule(unittest.TestCase):
	def test_cash_paid_opens_the_drawer(self):
		self.assertTrue(service.drawer_wanted(cash_paid=1100, change=0))

	def test_change_opens_the_drawer(self):
		self.assertTrue(service.drawer_wanted(cash_paid=0, change=400))

	def test_cashless_does_not(self):
		self.assertFalse(service.drawer_wanted(cash_paid=0, change=0))

	def test_nothing_or_none_is_no_cash(self):
		self.assertFalse(service.drawer_wanted(cash_paid=None, change=None))


class TestConfig(unittest.TestCase):
	def test_defaults_follow_the_protocol(self):
		self.assertEqual(service.PrinterConfig(address="p", protocol="epos").effective_port, 80)
		self.assertEqual(service.PrinterConfig(address="p", protocol="escpos").effective_port, 9100)
		self.assertEqual(service.PrinterConfig(address="p", protocol="escpos", port=9101).effective_port, 9101)

	def test_a_wrong_protocol_or_paper_is_refused(self):
		with self.assertRaises(ValueError):
			service.PrinterConfig(address="p", protocol="cups")
		with self.assertRaises(ValueError):
			service.PrinterConfig(address="p", paper_mm=70)
		with self.assertRaises(ValueError):
			service.PrinterConfig(address="")


class TestSettingsCheck(unittest.TestCase):
	"""What the form of the printer refuses before it is saved (the controller of URY Receipt Printer calls this)."""

	def ok(self, **over):
		fields = dict(address="192.168.1.20", protocol="ePOS-Print", port=0, paper_width="80", drawer_pin="2", drawer_pulse_ms=100)
		fields.update(over)
		return service.check_settings(**fields)

	def test_a_good_setting_passes(self):
		self.ok()
		self.ok(address="ury-printer.lan", protocol="ESC/POS (port 9100)", port=9100, paper_width="58", drawer_pin="5", drawer_pulse_ms=200)

	def test_the_address_is_a_host_not_a_url(self):
		for bad in ("", "  ", "http://192.168.1.20", "192.168.1.20/epos", "192.168.1.20:80", "a b"):
			with self.assertRaises(ValueError, msg=repr(bad)):
				self.ok(address=bad)

	def test_the_port_is_empty_or_a_real_port(self):
		self.ok(port=0)
		self.ok(port=8008)
		for bad in (-1, 70000):
			with self.assertRaises(ValueError):
				self.ok(port=bad)

	def test_paper_pin_and_pulse_are_the_known_ones(self):
		with self.assertRaises(ValueError):
			self.ok(paper_width="70")
		with self.assertRaises(ValueError):
			self.ok(drawer_pin="3")
		with self.assertRaises(ValueError):
			self.ok(drawer_pulse_ms=5)
		with self.assertRaises(ValueError):
			self.ok(drawer_pulse_ms=2000)

	def test_the_protocol_is_one_of_the_two(self):
		with self.assertRaises(ValueError):
			self.ok(protocol="CUPS")

	def test_the_config_is_built_from_the_saved_row(self):
		config = service.config_from_row(
			{"address": "10.0.0.5", "protocol": "ESC/POS (port 9100)", "port": 0, "paper_width": "58", "has_drawer": 1, "drawer_pin": "5", "drawer_pulse_ms": 200}
		)
		self.assertEqual((config.protocol, config.effective_port, config.paper_mm, config.pin, config.on_ms), ("escpos", 9100, 58, 1, 200))
		self.assertTrue(config.has_drawer)


class TestEposPrinter(unittest.TestCase):
	def setUp(self):
		renderer.calls.clear()
		self.printer = FakeEpos()
		self.addCleanup(self.printer.server_close)
		self.addCleanup(self.printer.shutdown)
		self.config = service.PrinterConfig(address="127.0.0.1", protocol="epos", port=self.printer.port, paper_mm=58)

	def test_a_bill_is_printed_without_the_drawer(self):
		result = service.send(self.config, html="<p>bill</p>", pulse=False, renderer=renderer)
		self.assertTrue(result.ok, result.message)
		self.assertEqual(renderer.calls, [("<p>bill</p>", 58)])
		body = self.printer.received[0][2]
		self.assertIn("<image", body)
		self.assertIn("<cut", body)
		self.assertNotIn("<pulse", body)

	def test_the_drawer_pulse_rides_in_the_print_job(self):
		result = service.send(self.config, html="<p>receipt</p>", pulse=True, renderer=renderer)
		self.assertTrue(result.ok, result.message)
		self.assertIn("<pulse", self.printer.received[0][2])

	def test_the_drawer_alone_prints_nothing(self):
		result = service.send(self.config, html=None, pulse=True, renderer=renderer)
		self.assertTrue(result.ok, result.message)
		body = self.printer.received[0][2]
		self.assertIn("<pulse", body)
		self.assertNotIn("<image", body)
		self.assertEqual(renderer.calls, [])

	def test_a_printer_without_a_drawer_ignores_the_pulse(self):
		config = service.PrinterConfig(address="127.0.0.1", protocol="epos", port=self.printer.port, has_drawer=False)
		result = service.send(config, html="<p>x</p>", pulse=True, renderer=renderer)
		self.assertTrue(result.ok, result.message)
		self.assertNotIn("<pulse", self.printer.received[0][2])

	def test_the_drawer_alone_on_a_printer_without_a_drawer_says_so(self):
		config = service.PrinterConfig(address="127.0.0.1", protocol="epos", port=self.printer.port, has_drawer=False)
		result = service.send(config, html=None, pulse=True, renderer=renderer)
		self.assertFalse(result.ok)
		self.assertIn("引き出し", result.message)
		self.assertEqual(self.printer.received, [])


class TestPrinterTroubles(unittest.TestCase):
	def test_paper_out_is_a_sentence_not_an_exception(self):
		printer = FakeEpos(reply='<response success="false" code="EPTR_REC_EMPTY" status="0"/>')
		self.addCleanup(printer.server_close)
		self.addCleanup(printer.shutdown)
		config = service.PrinterConfig(address="127.0.0.1", protocol="epos", port=printer.port)
		result = service.send(config, html="<p>x</p>", pulse=False, renderer=renderer)
		self.assertFalse(result.ok)
		self.assertIn("紙", result.message)

	def test_a_printer_that_is_off_is_a_sentence(self):
		config = service.PrinterConfig(address="127.0.0.1", protocol="epos", port=9, timeout=1)
		result = service.send(config, html="<p>x</p>", pulse=False, renderer=renderer)
		self.assertFalse(result.ok)
		self.assertIn("接続できません", result.message)

	def test_a_rendering_failure_is_a_sentence_and_nothing_is_sent(self):
		printer = FakeEpos()
		self.addCleanup(printer.server_close)
		self.addCleanup(printer.shutdown)
		config = service.PrinterConfig(address="127.0.0.1", protocol="epos", port=printer.port)
		result = service.send(config, html="<p>x</p>", pulse=False, renderer=failing_renderer)
		self.assertFalse(result.ok)
		self.assertEqual(printer.received, [])

	def test_a_failed_drawer_tells_the_cashier_to_use_the_key(self):
		config = service.PrinterConfig(address="127.0.0.1", protocol="epos", port=9, timeout=1)
		result = service.send(config, html=None, pulse=True, renderer=renderer)
		self.assertFalse(result.ok)
		self.assertIn("鍵", result.message)


class TestRawPrinter(unittest.TestCase):
	def test_a_receipt_with_the_drawer_over_port_9100(self):
		printer = FakeRaw()
		config = service.PrinterConfig(address="127.0.0.1", protocol="escpos", port=printer.port)
		result = service.send(config, html="<p>x</p>", pulse=True, renderer=renderer)
		printer.thread.join(3)
		self.assertTrue(result.ok, result.message)
		self.assertTrue(printer.asked)  # the paper sensor was asked first
		self.assertIn(b"\x1dv0", printer.job)
		self.assertTrue(printer.job.endswith(b"\x1bp\x00\x32\xfa") or b"\x1bp" in printer.job)

	def test_the_drawer_alone_over_port_9100(self):
		printer = FakeRaw()
		config = service.PrinterConfig(address="127.0.0.1", protocol="escpos", port=printer.port)
		result = service.send(config, html=None, pulse=True, renderer=renderer)
		printer.thread.join(3)
		self.assertTrue(result.ok, result.message)
		self.assertIn(b"\x1bp", printer.job)
		self.assertNotIn(b"\x1dv0", printer.job)

	def test_paper_out_over_port_9100(self):
		printer = FakeRaw(paper_status=b"\x72")
		config = service.PrinterConfig(address="127.0.0.1", protocol="escpos", port=printer.port)
		result = service.send(config, html="<p>x</p>", pulse=False, renderer=renderer)
		self.assertFalse(result.ok)
		self.assertIn("紙", result.message)


if __name__ == "__main__":
	unittest.main()
