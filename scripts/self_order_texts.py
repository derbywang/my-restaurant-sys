"""Write docs/design/self-order-texts.xlsx and .csv: the fixed texts of the customer ordering page in ja / en / zh / ko,
for the people who proofread them. Source: self-order/src/i18n/locales/*.json. Run with the bench's Python
(`env/bin/python apps/ury/scripts/self_order_texts.py`); needs openpyxl."""

import csv
import json
import os

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = os.path.join(os.path.dirname(__file__), "..")
LOCALES = os.path.join(ROOT, "self-order", "src", "i18n", "locales")
OUT = os.path.join(ROOT, "docs", "design", "self-order-texts")

# the wording the owner and the store manager confirm (the guest reads them as the shop speaking)
CONFIRM_KEYS = {
	"age.question": "年齢確認：お店と店長が確認",
	"age.note": "年齢確認：お店と店長が確認",
	"age.yes": "年齢確認",
	"age.no": "年齢確認",
	"pay.request_bill": "お会計の呼び出し：お店と店長が確認",
	"pay.bill_requested": "お会計の呼び出し：お店と店長が確認",
	"bill_switch.title": "会計伝票の切り替え案内：お店と店長が確認",
	"bill_switch.message": "会計伝票の切り替え案内：お店と店長が確認",
	"bill_switch.staff": "会計伝票の切り替え案内：お店と店長が確認",
	"split.title": "会計分割の案内：お店と店長が確認",
	"split.message": "会計分割の案内：お店と店長が確認",
}


def flat(data, prefix=""):
	for key, value in data.items():
		if isinstance(value, dict):
			yield from flat(value, f"{prefix}{key}.")
		else:
			yield f"{prefix}{key}", value


def load(lang):
	with open(os.path.join(LOCALES, f"{lang}.json"), encoding="utf-8") as f:
		return dict(flat(json.load(f)))


ja, en, zh, ko = (load(lang) for lang in ("ja", "en", "zh", "ko"))
header = ["key", "日本語 (ja)", "English (en)", "简体中文 草稿 (zh) ※机器翻译，未校对", "한국어 초안 (ko) ※机器翻译，未校对", "中文 校对后", "韩文 校对后", "备注"]
rows = [[key, ja[key], en[key], zh[key], ko[key], "", "", CONFIRM_KEYS.get(key, "")] for key in ja]

with open(OUT + ".csv", "w", newline="", encoding="utf-8-sig") as f:
	writer = csv.writer(f)
	writer.writerow(header)
	writer.writerows(rows)

book = openpyxl.Workbook()
sheet = book.active
sheet.title = "texts"
sheet.append(header)
for row in rows:
	sheet.append(row)
head_fill = PatternFill("solid", fgColor="DDDDDD")
for cell in sheet[1]:
	cell.font = Font(bold=True)
	cell.fill = head_fill
	cell.alignment = Alignment(wrap_text=True, vertical="top")
for index, width in enumerate((26, 38, 38, 38, 38, 38, 38, 30), start=1):
	sheet.column_dimensions[get_column_letter(index)].width = width
for row in sheet.iter_rows(min_row=2):
	for cell in row:
		cell.alignment = Alignment(wrap_text=True, vertical="top")
	if row[7].value:
		for cell in row:
			cell.fill = PatternFill("solid", fgColor="FFF2CC")
sheet.freeze_panes = "B2"
book.save(OUT + ".xlsx")
print(len(rows), "texts ->", OUT + ".xlsx")
