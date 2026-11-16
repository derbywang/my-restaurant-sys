"""ESC/POS commands as bytes (Epson command reference; TM-m30III)."""

ESC = b"\x1b"
GS = b"\x1d"
BAND_ROWS = 128  # a raster image is sent in bands: a printer's receive buffer is small


def initialize():
	return ESC + b"@"


def raster(bits, width_bytes, height):
	"""The image as GS v 0 bands. `bits`: width_bytes * height bytes, 1 = black, rows from the top."""
	if len(bits) != width_bytes * height:
		raise ValueError("the raster does not fit its width and height")
	out = b""
	for top in range(0, height, BAND_ROWS):
		rows = min(BAND_ROWS, height - top)
		band = bits[top * width_bytes : (top + rows) * width_bytes]
		out += GS + b"v0" + b"\x00" + _word(width_bytes) + _word(rows) + band
	return out


def feed(lines):
	return ESC + b"d" + bytes([max(0, min(255, lines))])


def cut(feed_first=True):
	"""Partial cut. Function B (GS V 66 n) feeds the paper to the cutting position, then cuts."""
	return GS + b"V" + (b"\x42\x03" if feed_first else b"\x01")


def kick(pin=0, on_ms=50, off_ms=500):
	"""The pulse that opens the cash drawer (ESC p m t1 t2): pin 0 is pin 2 of the drawer connector, 1 is pin 5.
	t1 and t2 are in units of 2 ms."""
	if pin not in (0, 1):
		raise ValueError("the pin is 0 (pin 2) or 1 (pin 5)")
	return ESC + b"p" + bytes([pin, max(1, min(255, on_ms // 2)), max(1, min(255, off_ms // 2))])


def job(bits=None, width_bytes=0, height=0, cut_paper=True, pulse=False, pin=0, on_ms=50, off_ms=500):
	"""initialize, the image (if any), the cut, and the drawer's pulse (if wanted). The pulse is sent after the cut so the
	drawer opens when the paper is out."""
	out = initialize()
	if bits:
		out += raster(bits, width_bytes, height) + feed(2)
	if cut_paper:
		out += cut()
	if pulse:
		out += kick(pin, on_ms, off_ms)
	return out


def _word(value):
	return bytes([value & 0xFF, (value >> 8) & 0xFF])
