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


PROTOCOL_LABELS = {"ePOS-Print": "epos", "ESC/POS (port 9100)": "escpos"}  # the Select values of the form -> protocol
PULSE_MS = (50, 500)  # what the drawer's pulse may be, in ms


def check_settings(address, protocol, port, paper_width, drawer_pin, drawer_pulse_ms):
	"""Refuse a printer setting that cannot work; ValueError with a sentence for the manager."""
	host = (address or "").strip()
	if not host or any(c in host for c in ("/", ":", " ")):
		raise ValueError("アドレスはプリンターの IP アドレスかホスト名だけを書いてください（http:// やポート番号は付けません）。")
	if protocol not in PROTOCOL_LABELS:
		raise ValueError("方式は「ePOS-Print」か「ESC/POS (port 9100)」から選んでください。")
	if not 0 <= int(port or 0) <= 65535:
		raise ValueError("ポートは 0（既定）から 65535 までの数字です。")
	if str(paper_width) not in ("80", "58"):
		raise ValueError("用紙幅は 80 mm か 58 mm です。")
	if str(drawer_pin) not in ("2", "5"):
		raise ValueError("引き出しのピンは 2 か 5 です。")
	if not PULSE_MS[0] <= int(drawer_pulse_ms or 0) <= PULSE_MS[1]:
		raise ValueError("引き出しのパルスは %d〜%d ミリ秒の間で指定してください。" % PULSE_MS)


def config_from_row(row):
	"""A PrinterConfig from a saved URY Receipt Printer (a dict or a document)."""
	get = row.get
	return PrinterConfig(
		address=(get("address") or "").strip(),
		protocol=PROTOCOL_LABELS.get(get("protocol"), "epos"),
		port=int(get("port") or 0),
		paper_mm=int(get("paper_width") or 80),
		has_drawer=bool(get("has_drawer")),
		pin=0 if str(get("drawer_pin") or "2") == "2" else 1,
		on_ms=int(get("drawer_pulse_ms") or 100),
	)


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
