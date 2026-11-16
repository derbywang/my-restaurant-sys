"""The receipt's HTML as a black and white raster for the printer (wkhtmltoimage + Pillow).

The printer prints 8 dots per millimetre; the printable width is 72 mm on 80 mm paper (576 dots) and 48 mm on 58 mm paper
(384 dots). wkhtmltoimage draws the page `dots` wide at a zoom that makes a CSS millimetre eight dots, so the text of the
template (written for 72 mm) fills the paper. The Japanese text is drawn by the server's fonts, not the printer's."""

import io
import subprocess

DOTS_PER_MM = 8
PRINTABLE_MM = {80: 72, 58: 48}
CSS_PX_PER_MM = 96 / 25.4
ZOOM = DOTS_PER_MM / CSS_PX_PER_MM  # 2.1167
THRESHOLD = 160


class RenderError(Exception):
	pass


def printable_dots(paper_mm):
	if paper_mm not in PRINTABLE_MM:
		raise ValueError("the paper is 80 or 58 mm wide")
	return PRINTABLE_MM[paper_mm] * DOTS_PER_MM


def fit_to_paper(html, paper_mm):
	"""The same page with the receipt's box as wide as the paper's printable width (the template says 72 mm)."""
	mm = PRINTABLE_MM[paper_mm]
	style = '<meta charset="utf-8"><style>body{margin:0;background:#fff}.jp-receipt{width:%dmm !important}</style>' % mm
	lowered = html.lower()
	at = lowered.find("<head>")
	if at >= 0:
		return html[: at + 6] + style + html[at + 6 :]
	return "<html><head>" + style + "</head><body>" + html + "</body></html>"


def render_png(html, paper_mm=80, run=subprocess.run, timeout=30):
	dots = printable_dots(paper_mm)
	command = [
		"wkhtmltoimage", "--quiet", "--format", "png", "--width", str(dots), "--zoom", "%.4f" % ZOOM, "--disable-smart-width",
		"-", "-",
	]
	try:
		done = run(command, input=fit_to_paper(html, paper_mm).encode("utf-8"), capture_output=True, timeout=timeout)
	except (OSError, subprocess.TimeoutExpired) as error:
		raise RenderError("小票の画像を作れません（wkhtmltoimage：%s）" % type(error).__name__) from error
	if not done.stdout:
		raise RenderError("小票の画像を作れません（wkhtmltoimage が画像を返しませんでした）")
	return done.stdout


def to_raster(png, paper_mm=80):
	"""(bits, width_bytes, height): 1 = black, rows from the top, the width is the paper's; the white below is cut off."""
	from PIL import Image

	dots = printable_dots(paper_mm)
	image = Image.open(io.BytesIO(png)).convert("RGBA")
	white = Image.new("RGBA", image.size, (255, 255, 255, 255))
	gray = Image.alpha_composite(white, image).convert("L")
	if gray.width != dots:
		gray = gray.resize((dots, max(1, round(gray.height * dots / gray.width))))
	black = gray.point(lambda value: 255 if value < THRESHOLD else 0)
	box = black.getbbox()
	height = min(gray.height, (box[3] + 8) if box else 1)  # a little paper under the last line
	black = black.crop((0, 0, dots, height)).convert("1")
	return black.tobytes(), dots // 8, height


def receipt_raster(html, paper_mm=80, run=subprocess.run):
	return to_raster(render_png(html, paper_mm, run), paper_mm)
