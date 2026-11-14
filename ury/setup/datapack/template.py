"""Builds the empty Excel file of the standard import format from `schema`:

    bench --site <site> execute ury.setup.datapack.template.build_template --args '["<path>.xlsx"]'
    (or: python -c "from ury.setup.datapack.template import build_template; build_template('<path>.xlsx')")
"""

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from ury.setup.datapack import schema

HEADER_ROW, HOW_ROW, EXAMPLE_ROW, FIRST_DATA_ROW = 2, 3, 4, 5

# How many data rows each sheet is prepared for (drop-downs and formulas run down to here).
CAPACITY = {"shop": 1, "rooms": 30, "tables": 200, "kitchens": 30, "courses": 100, "menu": 500, "staff": 100, "customers": 2000}

FONT = "Yu Gothic"
REQUIRED_FILL = PatternFill("solid", fgColor="C2410C")
OPTIONAL_FILL = PatternFill("solid", fgColor="475569")
FORMULA_FILL = PatternFill("solid", fgColor="E2E8F0")
HOW_FILL = PatternFill("solid", fgColor="F1F5F9")
EXAMPLE_FILL = PatternFill("solid", fgColor="FEF9C3")
THIN = Side(style="thin", color="CBD5E1")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def last_row(key):
	return FIRST_DATA_ROW + CAPACITY[key] - 1


def _list_source(sheet_key):
	source = schema.sheet(sheet_key)
	first = get_column_letter(1)
	return f"='{source.title}'!${first}${FIRST_DATA_ROW}:${first}${last_row(sheet_key)}"


def build_template(path):
	book = Workbook()
	_description(book.active)
	for sheet in schema.SHEETS:
		_sheet(book.create_sheet(sheet.title), sheet)
	book.save(path)
	return path


def _description(ws):
	ws.title = schema.DESCRIPTION_TITLE
	ws.sheet_view.showGridLines = False
	ws.column_dimensions["A"].width = 28
	ws.column_dimensions["B"].width = 26
	ws.column_dimensions["C"].width = 30
	row = 1
	for style, text in schema.DESCRIPTION:
		if style == "title":
			cell = ws.cell(row, 1, text)
			cell.font = Font(name=FONT, size=16, bold=True)
			ws.row_dimensions[row].height = 30
		elif style == "h":
			row += 1  # a blank line before every heading
			cell = ws.cell(row, 1, text)
			cell.font = Font(name=FONT, size=12, bold=True, color="FFFFFF")
			for c in range(1, 4):
				ws.cell(row, c).fill = OPTIONAL_FILL
		elif style == "table":
			for c, part in enumerate(text.split(" | "), start=1):
				cell = ws.cell(row, c, part)
				cell.font = Font(name=FONT, bold=(c == 1))
				cell.border = BOX
				cell.fill = HOW_FILL
		else:
			ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
			cell = ws.cell(row, 1, text)
			cell.font = Font(name=FONT)
			cell.alignment = Alignment(wrap_text=True, vertical="top")
			ws.row_dimensions[row].height = 18 * (1 + len(text) // 40)
		row += 1


def _sheet(ws, sheet):
	columns = sheet.columns
	count = len(columns)
	ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(count, 4))
	intro = ws.cell(1, 1, f"{sheet.title}：{sheet.intro}　（3行目は記入方法、4行目は記入例です。消さずに、5行目から入力してください）")
	intro.font = Font(name=FONT, bold=True)
	intro.alignment = Alignment(wrap_text=True, vertical="center")
	ws.row_dimensions[1].height = 48

	for index, column in enumerate(columns, start=1):
		letter = get_column_letter(index)
		ws.column_dimensions[letter].width = column.width
		header = ws.cell(HEADER_ROW, index, column.header)
		header.font = Font(name=FONT, bold=True, color="FFFFFF")
		header.fill = REQUIRED_FILL if column.required else OPTIONAL_FILL
		header.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
		header.border = BOX

		how = ws.cell(HOW_ROW, index, column.how)
		how.font = Font(name=FONT, size=9, italic=True, color="334155")
		how.fill = HOW_FILL
		how.alignment = Alignment(wrap_text=True, vertical="top")
		how.border = BOX

		example = ws.cell(EXAMPLE_ROW, index, column.example)
		example.font = Font(name=FONT, italic=True, color="854D0E")
		example.fill = EXAMPLE_FILL
		example.border = BOX
		example.alignment = Alignment(vertical="top")

	ws.row_dimensions[HEADER_ROW].height = 34
	ws.row_dimensions[HOW_ROW].height = 112
	ws.freeze_panes = "B3"

	end = FIRST_DATA_ROW + CAPACITY[sheet.key] - 1
	for index, column in enumerate(columns, start=1):
		letter = get_column_letter(index)
		area = f"{letter}{FIRST_DATA_ROW}:{letter}{end}"
		if column.kind == "formula":
			for row in range(FIRST_DATA_ROW, end + 1):
				cell = ws.cell(row, index, column.formula.format(row=row))
				cell.fill = FORMULA_FILL
				cell.number_format = "#,##0"
			continue
		validation = None
		if column.kind == "bool":
			validation = DataValidation(type="list", formula1=f'"{schema.MARK_YES},{schema.MARK_NO}"', allow_blank=True)
		elif column.kind == "choice" and column.choices:
			validation = DataValidation(type="list", formula1='"' + ",".join(column.choices) + '"', allow_blank=True)
		elif column.kind == "choice" and column.source:
			validation = DataValidation(type="list", formula1=_list_source(column.source), allow_blank=True)
		elif column.kind == "int":
			validation = DataValidation(type="whole", operator="greaterThanOrEqual", formula1="0", allow_blank=True)
			validation.error = "0以上の整数（半角）で入力してください。"
			validation.errorTitle = "数字を入力してください"
			validation.showErrorMessage = True
		if validation is not None:
			if column.kind in ("bool", "choice"):
				validation.error = "一覧から選んでください。"
				validation.errorTitle = "一覧にない値です"
				# a name of another sheet that is typed by hand is checked when the file is read
				validation.showErrorMessage = not column.source
			validation.add(area)
			ws.add_data_validation(validation)
