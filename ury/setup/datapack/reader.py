"""Reads a filled standard import file (see `schema`) into rows by column key.

    data, errors = read_pack(path)

`data[sheet key]` is a list of `Row(number, values)` (number = the row in the Excel file); `errors` are sentences for
the person who filled the file (sheet, row, what is wrong), all of them at once. The reader checks the file itself:
sheets and headers, required cells, types, the marks, choices, names used twice and names that point to another
sheet. Whether the pack fits the site (branch exists, ...) is the importer's job. Nothing is written anywhere."""

import re
import unicodedata
from dataclasses import dataclass

from openpyxl import load_workbook

from ury.setup.datapack import schema

HEADER_ROW, FIRST_DATA_ROW = 2, 5

YES = {"○", "〇", "◯", "●", "o", "yes", "y", "true", "1"}
NO = {"×", "✕", "✗", "x", "no", "n", "false", "0"}
UNIQUE = {"rooms": "name", "tables": "name", "kitchens": "name", "courses": "name", "menu": "name", "staff": "email"}
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass
class Row:
	number: int
	values: dict


def read_pack(path):
	book = load_workbook(path)
	data = {sheet.key: [] for sheet in schema.SHEETS}
	errors = []
	for sheet in schema.SHEETS:
		if sheet.title not in book.sheetnames:
			errors.append(f"シート「{sheet.title}」が見つかりません。")
			continue
		ws = book[sheet.title]
		if not _headers_ok(ws, sheet, errors):
			continue
		data[sheet.key] = _rows(ws, sheet, errors)
	_check_names(data, errors)
	return data, errors


def _headers_ok(ws, sheet, errors):
	ok = True
	for index, column in enumerate(sheet.columns, start=1):
		found = ws.cell(HEADER_ROW, index).value
		found = "" if found is None else str(found).strip()
		if found != column.header:
			errors.append(
				f"シート「{sheet.title}」の見出しが違います：{ws.cell(HEADER_ROW, index).coordinate} は「{column.header}」のはずですが「{found}」になっています。"
			)
			ok = False
	return ok


def _rows(ws, sheet, errors):
	rows = []
	data_columns = [(i, c) for i, c in enumerate(sheet.columns, start=1) if c.kind != "formula"]
	for number in range(FIRST_DATA_ROW, ws.max_row + 1):
		raw = {c.key: ws.cell(number, i).value for i, c in data_columns}
		if all(_blank(v) for v in raw.values()):
			continue
		values = {}
		for _i, column in data_columns:
			values[column.key] = _parse(sheet, column, raw[column.key], number, errors)
		rows.append(Row(number, values))
	return rows


def _blank(value):
	return value is None or (isinstance(value, str) and not value.strip())


def _where(sheet, number, column):
	return f"シート「{sheet.title}」{number}行目の「{column.header.rstrip('*')}」"


def _parse(sheet, column, value, number, errors):
	where = _where(sheet, number, column)
	if _blank(value):
		if column.required:
			errors.append(f"{where}が空です（必須の項目です）。")
		return column.default if column.kind == "bool" else (column.default if column.default is not None else None)

	if column.kind == "bool":
		mark = unicodedata.normalize("NFKC", str(value)).strip().lower()
		if mark in YES or str(value).strip() in YES:
			return True
		if mark in NO or str(value).strip() in NO:
			return False
		errors.append(f"{where}は ○ か × で書いてください（「{value}」は読み取れません）。")
		return column.default

	if column.kind == "int":
		number_value = _integer(value)
		if number_value is None:
			errors.append(f"{where}は0以上の整数で書いてください（「{value}」は読み取れません）。")
		return number_value

	text = _text(value)
	if column.kind == "choice" and column.choices and text not in column.choices:
		errors.append(f"{where}は {'・'.join(column.choices)} のどれかで書いてください（「{text}」は使えません）。")
	if column.key == "email" and sheet.key in ("staff", "customers") and not EMAIL.match(text):
		errors.append(f"{where}がメールの形式ではありません（「{text}」）。")
	return text


def _text(value):
	if isinstance(value, float) and value.is_integer():
		value = int(value)
	return str(value).strip()


def _integer(value):
	if isinstance(value, bool):
		return None
	if isinstance(value, (int, float)):
		return int(value) if float(value).is_integer() and value >= 0 else None
	cleaned = unicodedata.normalize("NFKC", str(value)).replace(",", "").replace("円", "").replace("¥", "").strip()
	if re.fullmatch(r"\d+(\.0+)?", cleaned):
		return int(float(cleaned))
	return None


def _check_names(data, errors):
	# a name used twice in one sheet
	for key, field in UNIQUE.items():
		seen = {}
		for row in data[key]:
			value = row.values.get(field)
			if not value:
				continue
			folded = value.lower() if field == "email" else value
			if folded in seen:
				sheet = schema.sheet(key)
				column = sheet.column(field)
				errors.append(
					f"シート「{sheet.title}」{row.number}行目の「{column.header.rstrip('*')}」「{value}」は{seen[folded]}行目と同じです（重複は使えません）。"
				)
			else:
				seen[folded] = row.number
	# a name that points to another sheet
	for sheet in schema.SHEETS:
		for column in sheet.columns:
			if not column.source:
				continue
			known = {r.values["name"] for r in data[column.source]}
			for row in data[sheet.key]:
				value = row.values.get(column.key)
				if value and value not in known:
					errors.append(
						f"{_where(sheet, row.number, column)}「{value}」が「{schema.sheet(column.source).title}」シートにありません。"
					)
