"""The test page of 「テスト印刷」 (the form of URY Receipt Printer): a frame as wide as the printable width, a mark at each side and a
ruler, so that one look at the paper says whether the paper width of the settings is right. A frame cut off on the right means the
setting is wider than the paper; empty paper on the right means it is narrower. No Frappe in here."""

from datetime import datetime

from ury.printing import bitmap

CELL_MM = 10


def test_page_html(paper_mm, address, protocol, now=None):
	mm = bitmap.PRINTABLE_MM[paper_mm]
	dots = bitmap.printable_dots(paper_mm)
	now = now or datetime.now()
	ruler = "".join(
		'<span style="display:inline-block;width:%dmm;height:16px;border-left:1px solid #000;font-size:10px;line-height:16px">&nbsp;%d</span>'
		% (CELL_MM, i * CELL_MM)
		for i in range(mm // CELL_MM + 1)
	)
	return (
		'<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>'
		'<div class="jp-receipt" style="border:2px solid #000;box-sizing:border-box;font-size:12px;line-height:1.5">'
		'<div style="text-align:center;font-size:16px;font-weight:bold;margin:4px 0">テスト印刷</div>'
		'<div style="white-space:nowrap;overflow:hidden;border-top:1px solid #000;border-bottom:1px solid #000">%s</div>'
		'<table style="width:100%%;border-collapse:collapse;margin:6px 0"><tr>'
		'<td style="font-size:18px;font-weight:bold;text-align:left">◀ 左</td>'
		'<td style="font-size:18px;font-weight:bold;text-align:right">右 ▶</td></tr></table>'
		'<div style="text-align:center;font-size:14px;font-weight:bold">紙幅 %d mm（%d 点）</div>'
		'<div style="text-align:center">アドレス %s</div>'
		'<div style="text-align:center">方式 %s</div>'
		'<div style="text-align:center;font-size:10px;margin-top:4px">%s</div>'
		'<div style="font-size:10px;margin:6px 4px 4px">枠の左右が紙の端まで見えれば、紙幅の設定は合っています。右が切れるときは設定が紙より広く、右が空くときは狭すぎます。</div>'
		"</div></body></html>"
	) % (ruler, paper_mm, dots, address, protocol, now.strftime("%Y-%m-%d %H:%M"))
