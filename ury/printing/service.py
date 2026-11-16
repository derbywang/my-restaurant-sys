"""What the server does with one printer's settings: draw the receipt, build the job, send it, say what went wrong.

No Frappe in here (the DocType and the endpoints are in ury/ury/api/receipt_print.py). `send` never raises: it returns a
`Result` whose `message` is a sentence for the cashier. A drawer that does not open must never undo a payment.
"""

from dataclasses import dataclass

from ury.printing import bitmap, epos, escpos, transport

PROTOCOLS = {"epos": 80, "escpos": transport.RAW_PORT}  # protocol -> default port
DRAWER_FAILED = "引き出しが開きませんでした。鍵で開けてください。"
NO_DRAWER = "このプリンターには引き出しが設定されていません。"


@dataclass
class PrinterConfig:
	address: str
	protocol: str = "epos"
	port: int = 0
	paper_mm: int = 80
	has_drawer: bool = True
	pin: int = 0  # 0: connector pin 2, 1: pin 5 (ESC p m); ePOS-Print drawer_1 / drawer_2
	on_ms: int = 100
	off_ms: int = 500
	timeout: float = 8

	def __post_init__(self):
		if not self.address:
			raise ValueError("the printer has no address")
		if self.protocol not in PROTOCOLS:
			raise ValueError("unknown protocol: %s" % self.protocol)
		if self.paper_mm not in bitmap.PRINTABLE_MM:
			raise ValueError("paper width must be 80 or 58 mm")

	@property
	def effective_port(self):
		return self.port or PROTOCOLS[self.protocol]


@dataclass
class Result:
	ok: bool
	message: str = ""


def drawer_wanted(cash_paid, change):
	"""The drawer opens when cash came in or change goes out; a card or a bill for the guest does not."""
	return bool(cash_paid and cash_paid > 0) or bool(change and change > 0)


def send(config, html=None, pulse=False, renderer=bitmap.receipt_raster):
	"""Print `html` (None: nothing on paper) and/or pulse the drawer. The pulse rides in the print job."""
	pulse = bool(pulse)
	if html is None and pulse and not config.has_drawer:
		return Result(False, NO_DRAWER)
	pulse = pulse and config.has_drawer
	try:
		bits, width_bytes, height = (None, 0, 0) if html is None else renderer(html, config.paper_mm)
		cut_paper = html is not None
		if config.protocol == "epos":
			xml = epos.job(bits, width_bytes, height, cut_paper=cut_paper, pulse=pulse, drawer=config.pin + 1, on_ms=config.on_ms)
			transport.send_epos(config.address, xml, timeout=config.timeout, port=config.effective_port)
		else:
			data = escpos.job(bits, width_bytes, height, cut_paper=cut_paper, pulse=pulse, pin=config.pin, on_ms=config.on_ms, off_ms=config.off_ms)
			transport.send_raw(config.address, data, port=config.effective_port, timeout=config.timeout)
	except (transport.PrinterError, bitmap.RenderError) as error:
		message = str(error)
		return Result(False, message + (" " + DRAWER_FAILED if html is None else ""))
	return Result(True)
