"""The printing core (ury/printing) against fake printers: nothing here needs a site or a database.

Run:  cd apps/ury && ../../env/bin/python -m unittest ury.printing.test_printing_core
"""

import base64
import os
import shutil
import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from ury.printing import bitmap, epos, escpos, transport

RECEIPT = (
	'<html><head><meta charset="utf-8"></head><body><div class="jp-receipt" style="width:72mm;font-size:12px">'
	'<div style="text-align:center;font-size:16px;font-weight:bold">領収書</div>'
	"<p>まぐろ握り（並）　¥1,100</p></div></body></html>"
)
HAS_WKHTMLTOIMAGE = shutil.which("wkhtmltoimage") is not None


class TestEscpos(unittest.TestCase):
	def test_the_drawer_pulse(self):
		self.assertEqual(escpos.kick(), b"\x1bp\x00\x19\xfa")  # pin 2, 50 ms on, 500 ms off (units of 2 ms)
		self.assertEqual(escpos.kick(pin=1, on_ms=100, off_ms=200), b"\x1bp\x01\x32\x64")
		with self.assertRaises(ValueError):
			escpos.kick(pin=2)

	def test_the_cut_feeds_first(self):
		self.assertEqual(escpos.cut(), b"\x1dVB\x03")

	def test_a_raster_is_sent_in_bands(self):
		width_bytes, height = 72, 300
		bits = bytes(range(256)) * (width_bytes * height // 256 + 1)
		bits = bits[: width_bytes * height]
		out = escpos.raster(bits, width_bytes, height)
		header = b"\x1dv0\x00" + bytes([72, 0])
		self.assertEqual(out.count(header), 3)  # 128 + 128 + 44 rows
		self.assertEqual(len(out), 3 * (len(header) + 2) + len(bits))
		self.assertIn(header + bytes([128, 0]), out)
		self.assertIn(header + bytes([44, 0]), out)

	def test_a_raster_that_does_not_fit_is_refused(self):
		with self.assertRaises(ValueError):
			escpos.raster(b"\x00" * 10, 72, 2)

	def test_the_job_has_the_pulse_after_the_cut_and_only_when_wanted(self):
		bits = b"\xff" * 72 * 4
		plain = escpos.job(bits, 72, 4)
		with_pulse = escpos.job(bits, 72, 4, pulse=True)
		self.assertTrue(plain.startswith(b"\x1b@"))
		self.assertNotIn(b"\x1bp", plain)
		self.assertTrue(with_pulse.endswith(escpos.kick()))
		self.assertLess(with_pulse.index(escpos.cut()), with_pulse.index(b"\x1bp"))

	def test_a_job_of_a_pulse_alone_opens_the_drawer_without_paper(self):
		self.assertEqual(escpos.job(cut_paper=False, pulse=True), b"\x1b@" + escpos.kick())


class TestEposXml(unittest.TestCase):
	def test_the_job_carries_the_image_the_cut_and_the_pulse(self):
		bits = b"\x80" * 72 * 3
		xml = epos.job(bits, 72, 3, pulse=True, drawer=1, on_ms=100)
		self.assertIn('xmlns="http://www.epson-pos.com/schemas/2011/03/epos-print"', xml)
		self.assertIn('<image width="576" height="3" color="color_1" mode="mono"', xml)
		self.assertIn(base64.b64encode(bits).decode(), xml)
		self.assertIn('<cut type="feed"/>', xml)
		self.assertIn('<pulse drawer="drawer_1" time="pulse_100"/>', xml)

	def test_no_pulse_unless_wanted_and_the_pulse_length_is_one_the_printer_knows(self):
		self.assertNotIn("<pulse", epos.job(b"\x00" * 72, 72, 1))
		self.assertEqual(epos.pulse_time(50), "pulse_100")
		self.assertEqual(epos.pulse_time(260), "pulse_300")
		self.assertEqual(epos.pulse_time(900), "pulse_500")

	def test_a_pulse_alone(self):
		xml = epos.job(cut_paper=False, pulse=True)
		self.assertNotIn("<image", xml)
		self.assertNotIn("<cut", xml)
		self.assertIn("<pulse", xml)

	def test_the_reply(self):
		ok = epos.parse_reply('<?xml?><s:Envelope><s:Body><response success="true" code="" status="251658262" battery="0"/></s:Body></s:Envelope>')
		self.assertTrue(ok.ok)
		bad = epos.parse_reply('<response success="false" code="EPTR_REC_EMPTY" status="251658278" battery="0"/>')
		self.assertFalse(bad.ok)
		self.assertIn("紙", bad.message)
		cover = epos.parse_reply('<response success="false" code="EPTR_COVER_OPEN" status="1"/>')
		self.assertIn("カバー", cover.message)
		unknown = epos.parse_reply('<response success="false" code="SOMETHING_NEW" status="1"/>')
		self.assertIn("SOMETHING_NEW", unknown.message)
		self.assertIsNone(epos.parse_reply("<html>not a printer</html>"))


class FakeEpos(HTTPServer):
	"""A printer that speaks ePOS-Print over HTTP and records what it was sent."""

	def __init__(self, reply='<response success="true" code="" status="0"/>', status=200, delay=0):
		self.received = []
		self.reply, self.http_status, self.delay = reply, status, delay
		outer = self

		class Handler(BaseHTTPRequestHandler):
			def do_POST(self):
				body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
				outer.received.append((self.path, dict(self.headers), body.decode("utf-8")))
				if outer.delay:
					threading.Event().wait(outer.delay)
				try:
					self.send_response(outer.http_status)
					self.send_header("Content-Type", "text/xml")
					self.end_headers()
					self.wfile.write(("<s:Envelope><s:Body>%s</s:Body></s:Envelope>" % outer.reply).encode())
				except OSError:  # the caller gave up (a timeout test)
					pass

			def log_message(self, *args):
				pass

		super().__init__(("127.0.0.1", 0), Handler)
		self.thread = threading.Thread(target=self.serve_forever, daemon=True)
		self.thread.start()

	@property
	def port(self):
		return self.server_address[1]

	def stop(self):
		self.shutdown()
		self.server_close()


class TestSendEpos(unittest.TestCase):
	def setUp(self):
		self.printers = []

	def printer(self, **kwargs):
		fake = FakeEpos(**kwargs)
		self.printers.append(fake)
		return fake

	def tearDown(self):
		for fake in self.printers:
			fake.stop()

	def test_the_job_arrives_where_the_printer_expects_it(self):
		fake = self.printer()
		xml = epos.job(b"\xff" * 72, 72, 1, pulse=True)
		reply = transport.send_epos("127.0.0.1", xml, port=fake.port)
		self.assertTrue(reply.ok)
		path, headers, body = fake.received[0]
		self.assertTrue(path.startswith("/cgi-bin/epos/service.cgi?devid=local_printer&timeout="))
		self.assertTrue(headers["Content-Type"].startswith("text/xml"))
		self.assertEqual(body, xml)

	def test_a_printer_without_paper_is_an_error_with_the_reason(self):
		fake = self.printer(reply='<response success="false" code="EPTR_REC_EMPTY" status="1"/>')
		with self.assertRaises(transport.PrinterError) as caught:
			transport.send_epos("127.0.0.1", epos.job(), port=fake.port)
		self.assertIn("紙", str(caught.exception))

	def test_an_http_error_is_an_error(self):
		fake = self.printer(status=500)
		with self.assertRaises(transport.PrinterError) as caught:
			transport.send_epos("127.0.0.1", epos.job(), port=fake.port)
		self.assertIn("500", str(caught.exception))

	def test_an_answer_that_is_not_a_printers_is_an_error(self):
		fake = self.printer(reply="<p>hello</p>")
		with self.assertRaises(transport.PrinterError):
			transport.send_epos("127.0.0.1", epos.job(), port=fake.port)

	def test_a_printer_that_is_not_there_is_an_error_not_a_crash(self):
		with socket.socket() as s:
			s.bind(("127.0.0.1", 0))
			port = s.getsockname()[1]
		with self.assertRaises(transport.PrinterError) as caught:
			transport.send_epos("127.0.0.1", epos.job(), port=port, timeout=2)
		self.assertIn("接続できません", str(caught.exception))

	def test_a_printer_that_does_not_answer_in_time_is_an_error(self):
		fake = self.printer(delay=2)
		with self.assertRaises(transport.PrinterError):
			transport.send_epos("127.0.0.1", epos.job(), port=fake.port, timeout=0.5)


class FakeRaw:
	"""A printer on raw TCP: answers DLE EOT 4 (the paper sensor) and records the job."""

	def __init__(self, paper_status=b"\x12", answers=True):
		self.job = b""
		self.asked = False
		self.answers = answers
		self.paper_status = paper_status
		self.server = socket.socket()
		self.server.bind(("127.0.0.1", 0))
		self.server.listen(1)
		self.port = self.server.getsockname()[1]
		self.thread = threading.Thread(target=self.run, daemon=True)
		self.thread.start()

	def run(self):
		try:
			connection, _ = self.server.accept()
		except OSError:
			return
		with connection:
			connection.settimeout(2)
			data = b""
			try:
				while True:
					chunk = connection.recv(4096)
					if not chunk:
						break
					data += chunk
					if data.startswith(b"\x10\x04\x04") and not self.asked:
						self.asked = True
						data = data[3:]
						if self.answers:
							connection.sendall(self.paper_status)
			except OSError:
				pass
			self.job = data

	def stop(self):
		self.server.close()
		self.thread.join(timeout=3)


class TestSendRaw(unittest.TestCase):
	def test_the_job_arrives_after_the_paper_was_asked_about(self):
		fake = FakeRaw()
		data = escpos.job(b"\xff" * 72 * 2, 72, 2, pulse=True)
		transport.send_raw("127.0.0.1", data, port=fake.port)
		fake.stop()
		self.assertTrue(fake.asked)
		self.assertEqual(fake.job, data)

	def test_a_printer_that_says_its_paper_is_out_is_not_given_the_job(self):
		fake = FakeRaw(paper_status=b"\x72")
		with self.assertRaises(transport.PrinterError) as caught:
			transport.send_raw("127.0.0.1", escpos.job(b"\xff" * 72, 72, 1), port=fake.port)
		fake.stop()
		self.assertIn("紙", str(caught.exception))
		self.assertEqual(fake.job, b"")

	def test_a_printer_that_does_not_answer_the_question_still_gets_the_job(self):
		fake = FakeRaw(answers=False)
		data = escpos.job(b"\xff" * 72, 72, 1)
		transport.send_raw("127.0.0.1", data, port=fake.port)
		fake.stop()
		self.assertEqual(fake.job, data)

	def test_without_the_paper_check_only_the_job_is_sent(self):
		fake = FakeRaw()
		data = escpos.job(b"\xff" * 72, 72, 1)
		transport.send_raw("127.0.0.1", data, port=fake.port, check_paper=False)
		fake.stop()
		self.assertFalse(fake.asked)
		self.assertEqual(fake.job, data)

	def test_a_printer_that_is_not_there_is_an_error(self):
		with socket.socket() as s:
			s.bind(("127.0.0.1", 0))
			port = s.getsockname()[1]
		with self.assertRaises(transport.PrinterError) as caught:
			transport.send_raw("127.0.0.1", b"x", port=port, timeout=2)
		self.assertIn("接続できません", str(caught.exception))


# what frappe.get_print returns around the receipt: a banner with "Print" and "Get PDF", a grey gutter and a paper-sized box
# with padding (found in the browser test: the receipt came out pushed to the right and clipped, with the banner on top)
FRAPPE_PAGE = (
	'<!DOCTYPE html><html><head><meta charset="utf-8"><style>'
	"@media screen{.print-format-gutter{background-color:#d1d8dd;padding:30px 0px}"
	".print-format{background-color:white;border-radius:8px;max-width:8.3in;min-height:11.69in;padding:0.75in;margin:auto}"
	"@media(max-width:767px){.print-format{padding:0.2in}}}"
	".print-format td,.print-format th{vertical-align:top !important;padding:6px !important}"
	"</style></head><body>"
	'<div class="action-banner print-hide"><a class="p-2">Print</a><a class="p-2">Get PDF</a></div>'
	'<div class="print-format-gutter"><div class="print-format">'
	"<style>.jp-receipt{width:72mm;font-size:12px}.jp-receipt .r{text-align:right}@media screen{.jp-receipt{padding:8px}}</style>"
	'<div class="jp-receipt"><table style="width:100%"><tr><td>まぐろ握り（並）</td><td class="r">¥1,100</td></tr>'
	'<tr><td>合計（税込）</td><td class="r">¥1,100</td></tr></table></div>'
	"</div></div></body></html>"
)


def ink_columns(bits, width_bytes, height):
	return [x for x in range(width_bytes * 8) if any(bits[y * width_bytes + x // 8] & (0x80 >> (x % 8)) for y in range(height))]


def receipt_page(names, total="¥1,000", stamp=False):
	"""The real template (ury/templates/print_formats/ury_jp_receipt.html) drawn with made-up data, inside the page Frappe puts
	around it. Plain jinja2: the template only reads `r`, which the site would have made with `jp_receipt_data`."""
	import re

	import jinja2

	path = os.path.join(os.path.dirname(__file__), "..", "templates", "print_formats", "ury_jp_receipt.html")
	with open(path, encoding="utf-8") as f:
		source = re.sub(r"\{%-?\s*set r = jp_receipt_data\(doc\)\s*-?%\}", "", f.read())
	lines = [{"name": n, "qty": 1, "rate": "¥390", "amount": "¥390", "reduced": False} for n in names]
	r = {
		"company": "三友寿司", "branch": "三友寿司", "address": "", "phone": "", "registration_valid": True,
		"registration_number": "T1234567890123", "title": "領収書", "posting": "2026年11月17日 05:36", "order_type": "店内",
		"table": "MD-06", "merged": False, "invoices": [{"name": "INV-1", "lines": lines, "total": total}],
		"subtotal": total, "discount": "", "total": total, "paid": True, "methods": "現金", "cashless": [],
		"cash_received": "¥5,000", "cash_label": "お預かり", "change": "¥100", "has_reduced": False, "credit_note": "",
		"rates": [{"rate": "10%", "reduced": False, "discount": "", "gross": "", "taxable": total, "tax": "¥90"}],
		"stamp_box": "収入印紙" if stamp else "",
	}
	html = jinja2.Template(source).render(r=r, doc={"name": "INV-1"})
	return FRAPPE_PAGE.split('<div class="print-format-gutter">')[0] + '<div class="print-format-gutter"><div class="print-format">' + html + "</div></div></body></html>"


@unittest.skipUnless(HAS_WKHTMLTOIMAGE, "wkhtmltoimage is not installed")
@unittest.skipUnless(HAS_WKHTMLTOIMAGE, "wkhtmltoimage is not installed")
class TestThePaperWidthReachesThePrinter(unittest.TestCase):
	"""The raster's width in the job follows the paper (nothing is written down as 576): GS v 0 m xL xH yL yH, xL xH = bytes per row."""

	def job_header(self, paper):
		from ury.printing import service

		printer = FakeRaw()
		config = service.PrinterConfig(address="127.0.0.1", protocol="escpos", port=printer.port, paper_mm=paper)
		result = service.send(config, html=receipt_page(["コーラ"]), pulse=False)
		printer.thread.join(3)
		self.assertTrue(result.ok, result.message)
		return printer.job

	def test_58_mm_paper_sends_48_bytes_per_row_and_80_mm_sends_72(self):
		self.assertIn(b"\x1dv0\x00\x30\x00", self.job_header(58))  # 48 bytes = 384 dots
		self.assertNotIn(b"\x1dv0\x00\x48\x00", self.job_header(58))
		self.assertIn(b"\x1dv0\x00\x48\x00", self.job_header(80))  # 72 bytes = 576 dots

	def test_the_ePOS_image_takes_its_width_from_the_paper_too(self):
		from ury.printing import service

		for paper, dots in ((58, 384), (80, 576)):
			printer = FakeEpos()
			try:
				config = service.PrinterConfig(address="127.0.0.1", protocol="epos", port=printer.port, paper_mm=paper)
				self.assertTrue(service.send(config, html=receipt_page(["コーラ"]), pulse=False).ok)
				self.assertIn('<image width="%d"' % dots, printer.received[0][2])
			finally:
				printer.shutdown()
				printer.server_close()


@unittest.skipUnless(HAS_WKHTMLTOIMAGE, "wkhtmltoimage is not installed")
class TestTheReceiptOn58mmPaper(unittest.TestCase):
	def height(self, names, paper=58, **kwargs):
		_, _, height = bitmap.receipt_raster(receipt_page(names, **kwargs), paper)
		return height

	def test_a_long_dish_name_is_not_squeezed_into_a_narrow_column(self):
		# on 48 mm the name, the quantity and the amount cannot share a line: the name gets its own line (a name of 14
		# characters is one line, as a name of 3), the quantity and the amount the line below
		self.assertEqual(self.height(["0%ノンアルコールビール"]), self.height(["コーラ"]))

	def test_a_name_longer_than_a_line_goes_on_to_the_next_line_and_nothing_is_clipped(self):
		bits, width_bytes, height = bitmap.receipt_raster(receipt_page(["サーモン尽くし五貫盛・シャリ大盛り"]), 58)
		columns = ink_columns(bits, width_bytes, height)
		self.assertLessEqual(min(columns), 8)
		self.assertLessEqual(max(columns), 383)
		self.assertGreater(self.height(["サーモン尽くし五貫盛・シャリ大盛り"]), self.height(["コーラ"]))

	def test_80_mm_paper_keeps_the_one_line_layout(self):
		self.assertEqual(self.height(["0%ノンアルコールビール"], paper=80), self.height(["コーラ"], paper=80))
		# the two-line layout is for the narrow paper only: on 80 mm a dish takes one line, on 58 mm two
		self.assertLess(self.height(["コーラ"], paper=80) * 384 // 576 - 1, self.height(["コーラ"], paper=58))

	def test_the_stamp_box_of_a_large_receipt_fits_on_the_paper(self):
		bits, width_bytes, height = bitmap.receipt_raster(receipt_page(["寿司盛り合わせ"], total="¥54,849", stamp=True), 58)
		columns = ink_columns(bits, width_bytes, height)
		self.assertLessEqual(max(columns), 383)
		self.assertGreaterEqual(max(columns), 383 - 12)  # the box sits at the right edge (margin: 8px 0 0 auto)


class TestThePageAroundTheReceipt(unittest.TestCase):
	def test_the_banner_the_gutter_and_the_padding_are_taken_away(self):
		fitted = bitmap.fit_to_paper(FRAPPE_PAGE, 58)
		for rule in (".print-hide", ".action-banner", ".print-format-gutter", ".print-format"):
			self.assertIn(rule, fitted.split("</style>")[0] + fitted[fitted.find("<style>") :][:1500])
		self.assertIn("width:48mm", fitted.replace(" ", ""))

	@unittest.skipUnless(HAS_WKHTMLTOIMAGE, "wkhtmltoimage is not installed")
	def test_the_receipt_fills_the_paper_from_its_left_edge_to_its_right_edge(self):
		for paper, dots in ((80, 576), (58, 384)):
			bits, width_bytes, height = bitmap.receipt_raster(FRAPPE_PAGE, paper)
			columns = ink_columns(bits, width_bytes, height)
			self.assertEqual(width_bytes * 8, dots)
			self.assertLessEqual(min(columns), 8, "%d mm: the receipt starts at the left edge" % paper)
			self.assertGreaterEqual(max(columns), dots - 12, "%d mm: the amounts end at the right edge" % paper)

	@unittest.skipUnless(HAS_WKHTMLTOIMAGE, "wkhtmltoimage is not installed")
	def test_the_banner_is_not_drawn(self):
		with_banner = FRAPPE_PAGE
		without_banner = FRAPPE_PAGE.replace('<div class="action-banner print-hide"><a class="p-2">Print</a><a class="p-2">Get PDF</a></div>', "")
		self.assertEqual(bitmap.receipt_raster(with_banner, 58), bitmap.receipt_raster(without_banner, 58))


@unittest.skipUnless(HAS_WKHTMLTOIMAGE, "wkhtmltoimage is not installed")
class TestBitmap(unittest.TestCase):
	def test_80_mm_paper_is_576_dots_wide_and_the_text_fills_it(self):
		bits, width_bytes, height = bitmap.receipt_raster(RECEIPT, 80)
		self.assertEqual(width_bytes * 8, 576)
		self.assertEqual(len(bits), width_bytes * height)
		self.assertGreater(height, 20)
		self.assertGreater(sum(bin(byte).count("1") for byte in bits), 200)  # there is ink
		columns = [x for x in range(576) if any(bits[y * width_bytes + x // 8] & (0x80 >> (x % 8)) for y in range(height))]
		self.assertGreater(max(columns), 576 * 0.5)  # the text is scaled to the paper, not a narrow strip

	def test_58_mm_paper_is_384_dots_wide(self):
		bits, width_bytes, height = bitmap.receipt_raster(RECEIPT, 58)
		self.assertEqual(width_bytes * 8, 384)
		self.assertEqual(len(bits), width_bytes * height)

	def test_the_white_below_the_last_line_is_cut_off(self):
		_, _, short = bitmap.receipt_raster(RECEIPT, 80)
		_, _, tall = bitmap.receipt_raster(RECEIPT.replace("</div></body>", "</div><div style='height:900px'></div></body>"), 80)
		self.assertEqual(short, tall)

	def test_a_page_with_nothing_on_it_is_a_small_blank_not_a_crash(self):
		bits, width_bytes, height = bitmap.receipt_raster("<html><body></body></html>", 80)
		self.assertEqual(len(bits), width_bytes * height)

	def test_the_paper_is_80_or_58(self):
		with self.assertRaises(ValueError):
			bitmap.printable_dots(70)

	def test_a_missing_renderer_is_a_sentence_for_the_owner(self):
		def missing(*args, **kwargs):
			raise FileNotFoundError("wkhtmltoimage")

		with self.assertRaises(bitmap.RenderError):
			bitmap.render_png(RECEIPT, 80, run=missing)

	def test_the_receipt_goes_through_both_protocols(self):
		bits, width_bytes, height = bitmap.receipt_raster(RECEIPT, 80)
		fake = FakeEpos()
		try:
			transport.send_epos("127.0.0.1", epos.job(bits, width_bytes, height, pulse=True), port=fake.port)
			self.assertIn(base64.b64encode(bits).decode(), fake.received[0][2])
		finally:
			fake.stop()
		raw = FakeRaw()
		data = escpos.job(bits, width_bytes, height, pulse=True)
		transport.send_raw("127.0.0.1", data, port=raw.port)
		raw.stop()
		self.assertEqual(raw.job, data)


if __name__ == "__main__":
	unittest.main()
