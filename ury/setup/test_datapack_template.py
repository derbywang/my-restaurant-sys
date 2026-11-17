"""The standard import format (data pack, docs/design/data-pack.md): the Excel template and the reader.

The template is made from one description of the sheets and columns (`ury.setup.datapack.schema`), which the
importer reads too, so what the shop is asked to fill in and what the importer expects cannot drift apart. No site
data is touched: these tests work on files in a temporary folder.
"""

import os
import tempfile
import unittest

from openpyxl import Workbook, load_workbook

from ury.setup.datapack import reader, schema, template

HEADER_ROW, HOW_ROW, EXAMPLE_ROW, FIRST_DATA_ROW = 2, 3, 4, 5


class WithTemplate(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.folder = tempfile.TemporaryDirectory()
		cls.path = os.path.join(cls.folder.name, "template.xlsx")
		template.build_template(cls.path)

	@classmethod
	def tearDownClass(cls):
		cls.folder.cleanup()

	def filled(self, rows_by_sheet):
		"""A copy of the template with rows written from row 5; `rows_by_sheet` is {sheet key: [[cell, ...], ...]}."""
		book = load_workbook(self.path)
		for key, rows in rows_by_sheet.items():
			ws = book[schema.sheet(key).title]
			for r, row in enumerate(rows):
				for c, value in enumerate(row):
					ws.cell(FIRST_DATA_ROW + r, c + 1).value = value
		path = os.path.join(self.folder.name, "filled.xlsx")
		book.save(path)
		return path


def _lists(ws):
	"""{column number: the choices (or the range) of the drop-down of that column}"""
	return {next(iter(v.sqref.ranges)).min_col: v.formula1 for v in ws.data_validations.dataValidation}


class TestTheSchema(unittest.TestCase):
	def test_sheet_and_column_names_are_unique(self):
		self.assertEqual(len({s.key for s in schema.SHEETS}), len(schema.SHEETS))
		self.assertEqual(len({s.title for s in schema.SHEETS}), len(schema.SHEETS))
		for sheet in schema.SHEETS:
			self.assertEqual(len({c.key for c in sheet.columns}), len(sheet.columns), sheet.title)
			self.assertEqual(len({c.header for c in sheet.columns}), len(sheet.columns), sheet.title)

	def test_every_column_says_how_to_fill_it_and_has_an_example(self):
		for sheet in schema.SHEETS:
			for column in sheet.columns:
				self.assertTrue(column.how.strip(), f"{sheet.title}/{column.header}: how to fill")
				self.assertTrue(str(column.example).strip(), f"{sheet.title}/{column.header}: example")

	def test_required_columns_are_marked_with_a_star(self):
		for sheet in schema.SHEETS:
			for column in sheet.columns:
				self.assertEqual(column.required, column.header.endswith("*"), f"{sheet.title}/{column.header}")

	def test_nothing_in_the_format_is_written_for_one_shop(self):
		"""Branch, profile and group names are read from the sheets: no name of 三友寿司 in the format."""
		for sheet in schema.SHEETS:
			for column in sheet.columns:
				for text in (column.header, column.how, str(column.example)):
					self.assertNotIn("三友", text, f"{sheet.title}/{column.header}")


class TestTheFormulasPointAtTheRightColumns(unittest.TestCase):
	def test_the_price_is_column_e_and_the_kind_is_column_c(self):
		menu = schema.sheet("menu")
		self.assertEqual(menu.columns.index(menu.column("price")), 4)  # E
		self.assertEqual(menu.columns.index(menu.column("kind")), 2)  # C


class TestTheTemplateFile(WithTemplate):
	def test_the_description_sheet_is_the_first_and_names_the_version(self):
		book = load_workbook(self.path)
		self.assertEqual(book.sheetnames[0], schema.DESCRIPTION_TITLE)
		text = " ".join(str(c.value) for row in book[schema.DESCRIPTION_TITLE].iter_rows() for c in row if c.value)
		self.assertIn(schema.FORMAT_VERSION, text)

	def description_of(self, sheet_key, column_key=None):
		sheet = schema.sheet(sheet_key)
		if column_key is None:
			return sheet.intro
		return next(c.how for c in sheet.columns if c.key == column_key)

	def test_the_variant_sheet_says_the_base_dishs_course_kind_and_kitchen_carry_over(self):
		text = self.description_of("variants") + self.description_of("variants", "base")
		for word in ("分類", "種類", "厨房", "基本の品と同じ"):
			self.assertIn(word, text)

	def test_the_price_says_taking_away_has_the_same_price_and_only_the_tax_differs(self):
		text = self.description_of("menu", "price")
		self.assertIn("持ち帰り", text)
		self.assertIn("同じ", text)
		self.assertIn("税率", text)

	def test_the_shop_sheet_says_the_example_row_is_not_imported(self):
		text = self.description_of("shop")
		self.assertIn("4行目", text)
		self.assertIn("取り込まれません", text)
		self.assertIn("5行目", text)

	def test_there_is_one_sheet_for_each_part_of_the_pack(self):
		book = load_workbook(self.path)
		self.assertEqual(book.sheetnames[1:], [s.title for s in schema.SHEETS])

	def test_the_header_row_how_row_and_example_row(self):
		book = load_workbook(self.path)
		for sheet in schema.SHEETS:
			ws = book[sheet.title]
			headers = [ws.cell(HEADER_ROW, i + 1).value for i in range(len(sheet.columns))]
			self.assertEqual(headers, [c.header for c in sheet.columns], sheet.title)
			for i, column in enumerate(sheet.columns):
				self.assertEqual(ws.cell(HOW_ROW, i + 1).value, column.how, f"{sheet.title}/{column.header}")
				self.assertEqual(str(ws.cell(EXAMPLE_ROW, i + 1).value), str(column.example), f"{sheet.title}/{column.header}")
				self.assertIsNone(ws.cell(FIRST_DATA_ROW, i + 1).value if not column.formula else None)

	def test_choices_are_drop_down_lists(self):
		book = load_workbook(self.path)
		ws = book[schema.sheet("menu").title]
		kind = schema.sheet("menu").column("kind")
		lists = _lists(ws)
		column_number = schema.sheet("menu").columns.index(kind) + 1
		self.assertEqual(lists[column_number], '"食品,酒類,非食品"')

	def test_yes_no_columns_offer_the_two_marks(self):
		book = load_workbook(self.path)
		ws = book[schema.sheet("menu").title]
		lists = _lists(ws)
		for key in ("self_order", "recommended", "stopped"):
			column = schema.sheet("menu").columns.index(schema.sheet("menu").column(key)) + 1
			self.assertEqual(lists[column], '"○,×"', key)

	def test_names_of_other_sheets_are_offered_for_the_course_the_kitchen_and_the_room(self):
		book = load_workbook(self.path)
		for sheet_key, column_key, source in (
			("menu", "course", "courses"),
			("menu", "kitchen", "kitchens"),
			("tables", "room", "rooms"),
		):
			ws = book[schema.sheet(sheet_key).title]
			column = schema.sheet(sheet_key).columns.index(schema.sheet(sheet_key).column(column_key)) + 1
			lists = _lists(ws)
			self.assertIn(schema.sheet(source).title, lists[column], f"{sheet_key}/{column_key}")

	def test_the_tax_included_prices_are_formulas_that_follow_the_kind(self):
		book = load_workbook(self.path)
		ws = book[schema.sheet("menu").title]
		menu = schema.sheet("menu")
		eat_in = menu.columns.index(menu.column("price_eat_in")) + 1
		take_away = menu.columns.index(menu.column("price_take_away")) + 1
		self.assertTrue(str(ws.cell(FIRST_DATA_ROW, eat_in).value).startswith("="))
		self.assertIn("1.08", str(ws.cell(FIRST_DATA_ROW, take_away).value))

	def test_the_two_rows_under_the_header_are_not_data(self):
		self.assertEqual(reader.FIRST_DATA_ROW, FIRST_DATA_ROW)


class TestReadingTheFilledFile(WithTemplate):
	def test_the_template_itself_holds_no_data(self):
		data, errors = reader.read_pack(self.path)
		self.assertEqual(errors, [])
		for sheet in schema.SHEETS:
			self.assertEqual(data[sheet.key], [], sheet.title)

	def test_rows_come_back_by_column_key_with_their_row_number(self):
		path = self.filled({"rooms": [["ホール", "1階"], ["個室"]]})
		data, errors = reader.read_pack(path)
		self.assertEqual(errors, [])
		self.assertEqual([r.number for r in data["rooms"]], [5, 6])
		self.assertEqual(data["rooms"][0].values, {"name": "ホール", "note": "1階"})
		self.assertEqual(data["rooms"][1].values, {"name": "個室", "note": None})

	def test_blank_rows_in_between_are_skipped_and_text_is_trimmed(self):
		path = self.filled({"rooms": [["  ホール "], [None], ["個室"]]})
		data, _errors = reader.read_pack(path)
		self.assertEqual([r.values["name"] for r in data["rooms"]], ["ホール", "個室"])

	def test_the_marks_are_read_as_booleans_and_blank_takes_the_default(self):
		menu = schema.sheet("menu")
		row = [None] * len(menu.columns)
		row[menu.columns.index(menu.column("name"))] = "まぐろ"
		row[menu.columns.index(menu.column("recommended"))] = "○"
		row[menu.columns.index(menu.column("stopped"))] = "×"
		data, _errors = reader.read_pack(self.filled({"menu": [row]}))
		values = data["menu"][0].values
		self.assertIs(values["recommended"], True)
		self.assertIs(values["stopped"], False)
		self.assertIs(values["self_order"], True)  # blank: the default of the column

	def test_a_number_cell_is_a_number_and_a_text_number_too(self):
		menu = schema.sheet("menu")
		row = [None] * len(menu.columns)
		row[0] = "まぐろ"
		price_at = menu.columns.index(menu.column("price"))
		row[price_at] = 1000
		data, _errors = reader.read_pack(self.filled({"menu": [row]}))
		self.assertEqual(data["menu"][0].values["price"], 1000)
		row[price_at] = "1,200"
		data, _errors = reader.read_pack(self.filled({"menu": [row]}))
		self.assertEqual(data["menu"][0].values["price"], 1200)

	def test_the_formula_columns_are_not_read(self):
		menu = schema.sheet("menu")
		data, _errors = reader.read_pack(self.filled({"menu": [["まぐろ"] + [None] * (len(menu.columns) - 1)]}))
		self.assertNotIn("price_eat_in", data["menu"][0].values)

	def test_a_row_with_only_formula_results_is_not_a_row(self):
		"""The tax-included columns hold formulas in every row: they alone do not make a menu line."""
		data, _errors = reader.read_pack(self.path)
		self.assertEqual(data["menu"], [])

	def test_a_missing_sheet_is_reported(self):
		book = Workbook()
		book.active.title = schema.DESCRIPTION_TITLE
		path = os.path.join(self.folder.name, "poor.xlsx")
		book.save(path)
		_data, errors = reader.read_pack(path)
		self.assertTrue(any(schema.sheet("menu").title in e and "シート" in e for e in errors), errors)

	def test_a_changed_header_is_reported(self):
		book = load_workbook(self.path)
		ws = book[schema.sheet("rooms").title]
		ws.cell(HEADER_ROW, 1).value = "部屋"
		path = os.path.join(self.folder.name, "renamed.xlsx")
		book.save(path)
		_data, errors = reader.read_pack(path)
		self.assertTrue(any(schema.sheet("rooms").title in e and "部屋" in e for e in errors), errors)

	def test_the_example_row_is_never_data(self):
		data, _errors = reader.read_pack(self.path)
		self.assertEqual(data["tables"], [])


class TestTheChecksOfTheReader(WithTemplate):
	def menu_row(self, **values):
		menu = schema.sheet("menu")
		row = [None] * len(menu.columns)
		base = {"name": "まぐろ", "course": "握り", "kind": "食品", "kitchen": "厨房", "price": 1000}
		base.update(values)
		for key, value in base.items():
			row[menu.columns.index(menu.column(key))] = value
		return row

	def pack(self, menu_rows, **others):
		rows = {"courses": [["握り"]], "kitchens": [["厨房"]], "menu": menu_rows}
		rows.update(others)
		return self.filled(rows)

	def test_a_good_menu_line_has_no_error(self):
		data, errors = reader.read_pack(self.pack([self.menu_row()]))
		self.assertEqual(errors, [])
		self.assertEqual(data["menu"][0].values["price"], 1000)
		self.assertEqual(data["menu"][0].values["course"], "握り")

	def test_a_required_cell_that_is_empty_is_reported_with_its_row(self):
		_data, errors = reader.read_pack(self.pack([self.menu_row(price=None)]))
		self.assertEqual(len(errors), 1, errors)
		self.assertIn("メニュー", errors[0])
		self.assertIn("5行目", errors[0])
		self.assertIn("税抜価格", errors[0])

	def test_a_kind_that_is_not_one_of_the_three_is_reported(self):
		_data, errors = reader.read_pack(self.pack([self.menu_row(kind="料理")]))
		self.assertTrue(any("種類" in e and "料理" in e for e in errors), errors)

	def test_a_price_with_decimals_is_reported(self):
		_data, errors = reader.read_pack(self.pack([self.menu_row(price=909.09)]))
		self.assertTrue(any("税抜価格" in e and "整数" in e for e in errors), errors)

	def test_a_mark_that_is_neither_circle_nor_cross_is_reported(self):
		_data, errors = reader.read_pack(self.pack([self.menu_row(recommended="はい")]))
		self.assertTrue(any("おすすめ" in e and "○" in e for e in errors), errors)

	def test_a_dish_name_used_twice_is_reported(self):
		_data, errors = reader.read_pack(self.pack([self.menu_row(), self.menu_row()]))
		self.assertTrue(any("5行目と同じ" in e and "6行目" in e for e in errors), errors)

	def test_a_course_that_is_not_in_the_course_sheet_is_reported(self):
		_data, errors = reader.read_pack(self.pack([self.menu_row(course="デザート")]))
		self.assertTrue(any("デザート" in e and "分類" in e and "シートにありません" in e for e in errors), errors)

	def test_a_kitchen_that_is_not_in_the_kitchen_sheet_is_reported(self):
		_data, errors = reader.read_pack(self.pack([self.menu_row(kitchen="寿司場")]))
		self.assertTrue(any("寿司場" in e for e in errors), errors)

	def test_a_table_in_a_room_that_does_not_exist_is_reported(self):
		_data, errors = reader.read_pack(self.filled({"rooms": [["ホール"]], "tables": [["T1", "テラス"]]}))
		self.assertTrue(any("テラス" in e for e in errors), errors)

	def test_an_email_that_is_not_an_email_is_reported(self):
		_data, errors = reader.read_pack(self.filled({"staff": [["山田", "yamada", "ホール"]]}))
		self.assertTrue(any("メールの形式" in e for e in errors), errors)

	def test_the_same_login_twice_is_reported_whatever_the_case(self):
		rows = [["A", "a@example.com", "ホール"], ["B", "A@example.com", "レジ担当"]]
		_data, errors = reader.read_pack(self.filled({"staff": rows}))
		self.assertTrue(any("6行目" in e and "5行目と同じ" in e for e in errors), errors)

	def test_a_role_that_is_not_one_of_the_four_is_reported(self):
		_data, errors = reader.read_pack(self.filled({"staff": [["A", "a@example.com", "オーナー"]]}))
		self.assertTrue(any("役割" in e and "オーナー" in e for e in errors), errors)

	def test_the_language_defaults_to_japanese(self):
		data, errors = reader.read_pack(self.filled({"staff": [["A", "a@example.com", "ホール"]]}))
		self.assertEqual(errors, [])
		self.assertEqual(data["staff"][0].values["language"], "ja")

	def test_a_phone_number_typed_as_a_number_is_kept_as_text(self):
		data, _errors = reader.read_pack(self.filled({"customers": [["田中", 9012345678]]}))
		self.assertEqual(data["customers"][0].values["phone"], "9012345678")


class TestVariantsAndToppings(WithTemplate):
	def variant_row(self, **values):
		sheet = schema.sheet("variants")
		row = [None] * len(sheet.columns)
		base = {"base": "にぎり（並）", "name": "にぎり（上）", "price": 1650}
		base.update(values)
		for key, value in base.items():
			row[sheet.columns.index(sheet.column(key))] = value
		return row

	def topping_row(self, **values):
		sheet = schema.sheet("toppings")
		row = [None] * len(sheet.columns)
		base = {"target": "にぎり（並）", "name": "大盛り", "price": 100}
		base.update(values)
		for key, value in base.items():
			row[sheet.columns.index(sheet.column(key))] = value
		return row

	def menu_with_the_base(self):
		menu = schema.sheet("menu")
		row = [None] * len(menu.columns)
		for key, value in {"name": "にぎり（並）", "course": "握り", "kind": "食品", "kitchen": "厨房", "price": 1100}.items():
			row[menu.columns.index(menu.column(key))] = value
		return {"courses": [["握り"]], "kitchens": [["厨房"]], "menu": [row]}

	def pack(self, variants=(), toppings=()):
		rows = self.menu_with_the_base()
		rows["variants"] = list(variants)
		rows["toppings"] = list(toppings)
		return self.filled(rows)

	def test_the_two_sheets_come_after_the_menu(self):
		titles = [s.title for s in schema.SHEETS]
		self.assertEqual(titles.index(schema.sheet("variants").title), titles.index(schema.sheet("menu").title) + 1)
		self.assertEqual(titles.index(schema.sheet("toppings").title), titles.index(schema.sheet("menu").title) + 2)

	def test_good_rows_are_read(self):
		data, errors = reader.read_pack(self.pack([self.variant_row()], [self.topping_row()]))
		self.assertEqual(errors, [])
		self.assertEqual(data["variants"][0].values["base"], "にぎり（並）")
		self.assertEqual(data["variants"][0].values["price"], 1650)
		self.assertIs(data["variants"][0].values["self_order"], True)
		self.assertEqual(data["toppings"][0].values["price"], 100)

	def test_a_variant_of_a_dish_that_is_not_on_the_menu_is_reported(self):
		_data, errors = reader.read_pack(self.pack([self.variant_row(base="ない品")]))
		self.assertTrue(any("ない品" in e and "メニュー" in e and "シートにありません" in e for e in errors), errors)

	def test_a_variant_named_like_a_dish_of_the_menu_is_reported(self):
		_data, errors = reader.read_pack(self.pack([self.variant_row(name="にぎり（並）")]))
		self.assertTrue(any("にぎり（並）" in e and "同じ" in e for e in errors), errors)

	def test_a_variant_name_used_twice_is_reported(self):
		_data, errors = reader.read_pack(self.pack([self.variant_row(), self.variant_row()]))
		self.assertTrue(any("6行目" in e and "5行目と同じ" in e for e in errors), errors)

	def test_a_topping_needs_a_dish_or_a_course(self):
		_data, errors = reader.read_pack(self.pack(toppings=[self.topping_row(target=None)]))
		self.assertTrue(any("対象の品名" in e and "対象の分類" in e for e in errors), errors)

	def test_a_topping_cannot_have_both_a_dish_and_a_course(self):
		_data, errors = reader.read_pack(self.pack(toppings=[self.topping_row(course="握り")]))
		self.assertTrue(any("どちらか" in e for e in errors), errors)

	def test_a_topping_for_a_course_that_does_not_exist_is_reported(self):
		_data, errors = reader.read_pack(self.pack(toppings=[self.topping_row(target=None, course="ない分類")]))
		self.assertTrue(any("ない分類" in e and "分類" in e for e in errors), errors)

	def test_the_same_topping_of_the_same_dish_twice_is_reported(self):
		_data, errors = reader.read_pack(self.pack(toppings=[self.topping_row(), self.topping_row()]))
		self.assertTrue(any("6行目" in e and "5行目と同じ" in e for e in errors), errors)

	def test_a_topping_can_name_a_variant_to_have_its_own_price(self):
		data, errors = reader.read_pack(self.pack([self.variant_row()], [self.topping_row(), self.topping_row(target="にぎり（上）", price=150)]))
		self.assertEqual(errors, [])
		self.assertEqual(data["toppings"][1].values["target"], "にぎり（上）")

	def test_the_price_of_a_topping_may_be_zero(self):
		data, errors = reader.read_pack(self.pack(toppings=[self.topping_row(price=0)]))
		self.assertEqual(errors, [])
		self.assertEqual(data["toppings"][0].values["price"], 0)

	def test_the_kind_of_a_topping_is_one_of_the_three_or_empty(self):
		_data, errors = reader.read_pack(self.pack(toppings=[self.topping_row(kind="料理")]))
		self.assertTrue(any("種類" in e and "料理" in e for e in errors), errors)
		data, errors = reader.read_pack(self.pack(toppings=[self.topping_row(kind="酒類")]))
		self.assertEqual(errors, [])
		self.assertEqual(data["toppings"][0].values["kind"], "酒類")
