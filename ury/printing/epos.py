"""ePOS-Print XML: the same job as `escpos.job`, and the printer's answer (Epson ePOS-Print XML user's manual)."""

import base64
import re
from xml.sax.saxutils import escape

NAMESPACE = "http://www.epson-pos.com/schemas/2011/03/epos-print"
PULSE_TIMES = (100, 200, 300, 400, 500)

# the codes the printer answers with when `success` is false -> what to tell the cashier (Japanese: they read it)
MESSAGES = {
	"EPTR_COVER_OPEN": "プリンターのカバーが開いています。閉めてください。",
	"EPTR_REC_EMPTY": "プリンターの紙がありません。紙を入れてください。",
	"EPTR_AUTORECOVER": "プリンターが自動復帰中です。少し待ってからもう一度お試しください。",
	"EPTR_BADPORT": "プリンターの通信ポートに問題があります。",
	"EPTR_TIMEOUT": "プリンターが応答しません。電源とネットワークを確認してください。",
	"EPTR_MECHANICAL": "プリンターの機械にエラーがあります（紙づまりなど）。",
	"EPTR_UNRECOVERABLE": "プリンターに回復できないエラーがあります。電源を入れ直してください。",
	"PRINT_FAILURE": "印刷に失敗しました。",
	"SchemaError": "プリンターが印刷データを受け付けませんでした。",
	"DeviceNotFound": "プリンターが見つかりません。",
	"EX_BADPORT": "プリンターの通信ポートに問題があります。",
}


class PrinterReply:
	def __init__(self, ok, code="", status="", message=""):
		self.ok = ok
		self.code = code
		self.status = status
		self.message = message


def pulse_time(on_ms):
	"""The nearest of the pulse lengths ePOS-Print knows (pulse_100 ... pulse_500)."""
	return "pulse_%d" % min(PULSE_TIMES, key=lambda t: abs(t - on_ms))


def job(bits=None, width_bytes=0, height=0, cut_paper=True, pulse=False, drawer=1, on_ms=100):
	"""The SOAP envelope the printer takes. `drawer`: 1 or 2."""
	parts = []
	if bits:
		if len(bits) != width_bytes * height:
			raise ValueError("the raster does not fit its width and height")
		parts.append(
			'<image width="%d" height="%d" color="color_1" mode="mono" align="left">%s</image>'
			% (width_bytes * 8, height, base64.b64encode(bits).decode("ascii"))
		)
		parts.append('<feed line="2"/>')
	if cut_paper:
		parts.append('<cut type="feed"/>')
	if pulse:
		parts.append('<pulse drawer="drawer_%d" time="%s"/>' % (drawer, pulse_time(on_ms)))
	return (
		'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
		'<epos-print xmlns="%s">%s</epos-print></s:Body></s:Envelope>' % (NAMESPACE, "".join(parts))
	)


def parse_reply(text):
	"""The `<response success=".." code=".." status=".."/>` in the answer; None when there is none."""
	match = re.search(r"<response\b([^>]*)>", text or "")
	if not match:
		return None
	attributes = dict(re.findall(r'(\w+)="([^"]*)"', match.group(1)))
	ok = attributes.get("success", "").lower() == "true"
	code = attributes.get("code", "")
	return PrinterReply(
		ok,
		code,
		attributes.get("status", ""),
		"" if ok else MESSAGES.get(code, "印刷に失敗しました（プリンターのコード：%s）。" % escape(code or "不明")),
	)
