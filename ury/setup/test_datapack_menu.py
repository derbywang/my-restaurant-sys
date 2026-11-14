"""The data pack imports the menu: courses, kitchens, item groups, dishes, prices (docs/design/data-pack.md, step 2).

`plan_menu` only reads and says what would be created, updated or left; `apply_menu` does it; importing the same
sheets again changes nothing. Everything runs in the rolled-back transaction of the test site.
"""

import os
import tempfile

import frappe
from erpnext.stock.get_item_details import get_item_tax_template

from ury.setup.datapack import importer
from ury.setup.datapack.reader import Row
from ury.setup.test_site import BRANCH, COMPANY, PRODUCTION_UNIT, RESTAURANT, URYTestCase

MENU = "DP通常メニュー"
KITCHEN_SUSHI = "DP寿司場"
KITCHEN_MAIN = "DP厨房"
COURSE = "DP握り"
COURSE_DRINK = "DP飲み物"
TUNA = "DPまぐろ握り"
BEER = "DPビール"


def rows(*values):
	return [Row(5 + i, v) for i, v in enumerate(values)]


def course(name, order=None, zh=None, ko=None, en=None):
	return {"name": name, "order": order, "zh": zh, "ko": ko, "en": en, "note": None}


def dish(name, course_name, kind, kitchen, price, **extra):
	values = {
		"name": name, "course": course_name, "kind": kind, "kitchen": kitchen, "price": price,
		"self_order": True, "recommended": False, "stopped": False, "zh": None, "ko": None, "en": None,
		"image": None, "note": None,
	}
	values.update(extra)
	return values


def pack(menu=None, **override):
	data = {
		"shop": rows({"branch": BRANCH, "restaurant": RESTAURANT, "menu": MENU, "profile": None}),
		"rooms": [],
		"tables": [],
		"kitchens": rows({"name": KITCHEN_SUSHI, "note": None}, {"name": KITCHEN_MAIN, "note": None}),
		"courses": rows(
			course(COURSE, 2, "握寿司", "니기리", "Nigiri"), course(COURSE_DRINK)
		),
		"menu": rows(
			dish(TUNA, COURSE, "食品", KITCHEN_SUSHI, 1000, recommended=True, zh="金枪鱼握寿司", ko="참치 니기리", en="Tuna nigiri"),
			dish(BEER, COURSE_DRINK, "酒類", KITCHEN_MAIN, 500, self_order=False),
		),
		"staff": [],
		"customers": [],
	}
	if menu is not None:
		data["menu"] = menu
	data.update(override)
	return data


def verbs(result):
	return {(a.doctype, a.name): a.verb for a in result.actions}


def tax_template(item, tax_category):
	args = {"company": COMPANY, "tax_category": tax_category, "posting_date": "2026-11-01", "base_net_rate": 100}
	return get_item_tax_template(args, frappe.get_cached_doc("Item", item), {})


def rate_of(item, rate_list=None):
	price_list = rate_list or frappe.db.get_value("URY Menu", MENU, "price_list")
	return frappe.db.get_value("Item Price", {"item_code": item, "price_list": price_list}, "price_list_rate")


class RolledBack(URYTestCase):
	"""Every test starts from the site as it is and leaves nothing behind (the tests of a class share one transaction)."""

	def setUp(self):
		super().setUp()
		frappe.db.savepoint("datapack_menu")

	def tearDown(self):
		frappe.db.rollback(save_point="datapack_menu")
		super().tearDown()


class TestPlan(RolledBack):
	def test_the_plan_says_what_would_be_created_and_writes_nothing(self):
		counts = {d: frappe.db.count(d) for d in ("Item", "Item Group", "URY Menu", "URY Menu Course", "URY Production Unit", "Item Price")}
		result = importer.plan_menu(pack())
		self.assertEqual(result.errors, [])
		seen = verbs(result)
		self.assertEqual(seen[("Item", TUNA)], "create")
		self.assertEqual(seen[("Item", BEER)], "create")
		self.assertEqual(seen[("URY Menu", MENU)], "create")
		self.assertEqual(seen[("URY Menu Course", COURSE)], "create")
		self.assertEqual(seen[("URY Production Unit", KITCHEN_SUSHI)], "create")
		self.assertEqual({d: frappe.db.count(d) for d in counts}, counts)

	def test_a_branch_that_is_not_there_is_an_error_that_points_to_the_wizard(self):
		data = pack(shop=rows({"branch": "存在しない店", "restaurant": RESTAURANT, "menu": MENU, "profile": None}))
		result = importer.plan_menu(data)
		self.assertTrue(any("存在しない店" in e and "セットアップウィザード" in e for e in result.errors), result.errors)

	def test_a_restaurant_of_another_branch_is_an_error(self):
		data = pack(shop=rows({"branch": BRANCH, "restaurant": "存在しない店", "menu": MENU, "profile": None}))
		result = importer.plan_menu(data)
		self.assertTrue(any("存在しない店" in e for e in result.errors), result.errors)

	def test_the_shop_sheet_needs_exactly_one_row(self):
		self.assertTrue(importer.plan_menu(pack(shop=[])).errors)
		two = rows(*[{"branch": BRANCH, "restaurant": RESTAURANT, "menu": MENU, "profile": None}] * 2)
		self.assertTrue(importer.plan_menu(pack(shop=two)).errors)

	def test_a_missing_image_file_is_an_error_naming_the_file(self):
		data = pack(menu=rows(dish(TUNA, COURSE, "食品", KITCHEN_SUSHI, 1000, image="maguro.jpg")))
		with tempfile.TemporaryDirectory() as folder:
			result = importer.plan_menu(data, folder=folder)
		self.assertTrue(any("maguro.jpg" in e and "images" in e for e in result.errors), result.errors)


class TestApply(RolledBack):
	def apply(self, data=None, **kwargs):
		result = importer.apply_menu(data or pack(), **kwargs)
		self.assertEqual(result.errors, [])
		return result

	def test_the_dishes_courses_kitchens_and_menu_are_made(self):
		self.apply()
		self.assertEqual(frappe.db.get_value("Item", TUNA, "item_name"), TUNA)
		self.assertEqual(frappe.db.get_value("Item", TUNA, "item_group"), f"{KITCHEN_SUSHI}（食品）")
		self.assertEqual(frappe.db.get_value("Item Group", f"{KITCHEN_SUSHI}（食品）", "parent_item_group"), "食品")
		self.assertEqual(frappe.db.get_value("Item", BEER, "item_group"), f"{KITCHEN_MAIN}（酒類）")
		self.assertEqual(frappe.db.get_value("Item Group", f"{KITCHEN_MAIN}（酒類）", "parent_item_group"), "酒類")
		self.assertEqual(frappe.db.get_value("URY Menu", MENU, "branch"), BRANCH)
		self.assertEqual(frappe.db.get_value("URY Restaurant", RESTAURANT, "active_menu"), MENU)

	def test_the_price_without_tax_is_the_price_of_the_menu(self):
		self.apply()
		self.assertEqual(rate_of(TUNA), 1000)
		self.assertEqual(rate_of(BEER), 500)

	def test_the_menu_line_has_the_flags_of_the_sheet(self):
		self.apply()
		line = frappe.get_all(
			"URY Menu Item", filters={"parent": MENU, "item": TUNA},
			fields=["course", "rate", "special_dish", "disabled", "self_order_allowed"],
		)[0]
		self.assertEqual((line.course, line.rate, line.special_dish, line.disabled, line.self_order_allowed), (COURSE, 1000, 1, 0, 1))
		beer = frappe.get_all("URY Menu Item", filters={"parent": MENU, "item": BEER}, fields=["self_order_allowed"])[0]
		self.assertEqual(beer.self_order_allowed, 0)

	def test_a_stopped_dish_stays_on_the_menu_but_is_disabled(self):
		data = pack(menu=rows(dish(TUNA, COURSE, "食品", KITCHEN_SUSHI, 1000, stopped=True)))
		self.apply(data)
		self.assertEqual(frappe.db.get_value("URY Menu Item", {"parent": MENU, "item": TUNA}, "disabled"), 1)

	def test_the_courses_have_their_order_and_names_in_the_languages(self):
		self.apply()
		self.assertEqual(frappe.db.get_value("URY Menu Course", COURSE, "custom_serving_priority"), 2)
		names = {r.language: r.label for r in frappe.get_all("URY Translation Row", filters={"parent": COURSE, "parentfield": "translations"}, fields=["language", "label"])}
		self.assertEqual(names, {"zh": "握寿司", "ko": "니기리", "en": "Nigiri"})
		self.assertFalse(frappe.get_all("URY Translation Row", filters={"parent": COURSE_DRINK}))

	def test_the_dishes_have_their_names_in_the_languages(self):
		self.apply()
		names = {r.language: r.label for r in frappe.get_all("URY Translation Row", filters={"parent": TUNA, "parentfield": "custom_translations"}, fields=["language", "label"])}
		self.assertEqual(names, {"zh": "金枪鱼握寿司", "ko": "참치 니기리", "en": "Tuna nigiri"})

	def test_each_kitchen_makes_the_groups_of_its_dishes(self):
		self.apply()
		groups = lambda unit: {r.item_group for r in frappe.get_all("URY Production Item Groups", filters={"parent": unit}, fields=["item_group"])}  # noqa: E731
		self.assertEqual(groups(KITCHEN_SUSHI), {f"{KITCHEN_SUSHI}（食品）"})
		self.assertEqual(groups(KITCHEN_MAIN), {f"{KITCHEN_MAIN}（酒類）"})
		self.assertEqual(frappe.db.get_value("URY Production Unit", KITCHEN_SUSHI, "branch"), BRANCH)
		self.assertTrue(frappe.db.get_value("URY Production Unit", KITCHEN_SUSHI, "pos_profile"))

	def test_a_kitchen_that_is_already_there_is_used_and_gets_the_new_groups(self):
		data = pack(kitchens=rows({"name": PRODUCTION_UNIT, "note": None}), menu=rows(dish(TUNA, COURSE, "食品", PRODUCTION_UNIT, 1000)))
		self.apply(data)
		groups = {r.item_group for r in frappe.get_all("URY Production Item Groups", filters={"parent": PRODUCTION_UNIT}, fields=["item_group"])}
		self.assertIn(f"{PRODUCTION_UNIT}（食品）", groups)
		self.assertFalse(frappe.db.exists("URY Production Unit", {"name": ["like", "DP%"]}))

	def test_the_tax_follows_the_kind_food_is_8_percent_to_go_and_the_beer_10(self):
		self.apply()
		take_away_food = tax_template(TUNA, "テイクアウト")
		eat_in_food = tax_template(TUNA, "店内飲食")
		take_away_beer = tax_template(BEER, "テイクアウト")
		self.assertIn("8", str(take_away_food))
		self.assertIn("10", str(eat_in_food))
		self.assertIn("10", str(take_away_beer))
		self.assertNotEqual(take_away_food, eat_in_food)

	def test_no_dish_is_left_without_a_kitchen(self):
		from ury.ury.api.kitchen_check import items_without_kitchen

		self.apply()
		self.assertEqual(items_without_kitchen(BRANCH, [TUNA, BEER]), [])

	def test_the_same_sheets_again_change_nothing(self):
		self.apply()
		second = importer.plan_menu(pack())
		self.assertEqual(second.errors, [])
		self.assertEqual({a.verb for a in second.actions}, {"same"})
		again = importer.apply_menu(pack())
		self.assertEqual({a.verb for a in again.actions}, {"same"})
		price_list = frappe.db.get_value("URY Menu", MENU, "price_list")
		self.assertEqual(frappe.db.count("Item Price", {"item_code": TUNA, "price_list": price_list}), 1)

	def test_a_new_price_is_an_update_and_reaches_the_price_list(self):
		self.apply()
		changed = pack(menu=rows(dish(TUNA, COURSE, "食品", KITCHEN_SUSHI, 1200), dish(BEER, COURSE_DRINK, "酒類", KITCHEN_MAIN, 500, self_order=False)))
		plan = importer.plan_menu(changed)
		self.assertEqual(verbs(plan)[("URY Menu", MENU)], "update")
		self.assertEqual(verbs(plan)[("Item", TUNA)], "update")
		self.assertEqual(verbs(plan)[("Item", BEER)], "same")
		self.apply(changed)
		self.assertEqual(rate_of(TUNA), 1200)
		self.assertEqual(rate_of(BEER), 500)

	def test_a_dish_that_is_not_in_the_sheet_any_more_is_kept_and_listed(self):
		self.apply()
		fewer = pack(menu=rows(dish(TUNA, COURSE, "食品", KITCHEN_SUSHI, 1000, recommended=True, zh="金枪鱼握寿司", ko="참치 니기리", en="Tuna nigiri")))
		result = self.apply(fewer)
		self.assertTrue(frappe.db.exists("URY Menu Item", {"parent": MENU, "item": BEER}))
		self.assertIn(BEER, [e for e in result.extra])

	def test_a_new_name_in_the_menu_is_added_to_the_menu_that_is_there(self):
		self.apply()
		more = pack(menu=rows(dish(TUNA, COURSE, "食品", KITCHEN_SUSHI, 1000, recommended=True, zh="金枪鱼握寿司", ko="참치 니기리", en="Tuna nigiri"), dish(BEER, COURSE_DRINK, "酒類", KITCHEN_MAIN, 500, self_order=False), dish("DPたまご", COURSE, "食品", KITCHEN_SUSHI, 200)))
		self.apply(more)
		self.assertTrue(frappe.db.exists("URY Menu Item", {"parent": MENU, "item": "DPたまご"}))
		self.assertEqual(rate_of("DPたまご"), 200)

	def test_a_dish_that_changes_kind_moves_to_the_group_of_the_new_kind(self):
		self.apply()
		changed = pack(menu=rows(dish(TUNA, COURSE, "非食品", KITCHEN_SUSHI, 1000), dish(BEER, COURSE_DRINK, "酒類", KITCHEN_MAIN, 500, self_order=False)))
		self.apply(changed)
		self.assertEqual(frappe.db.get_value("Item", TUNA, "item_group"), f"{KITCHEN_SUSHI}（非食品）")

	def test_an_error_in_the_plan_stops_the_apply_and_writes_nothing(self):
		bad = pack(shop=rows({"branch": "存在しない店", "restaurant": RESTAURANT, "menu": MENU, "profile": None}))
		before = frappe.db.count("Item")
		result = importer.apply_menu(bad)
		self.assertTrue(result.errors)
		self.assertEqual(frappe.db.count("Item"), before)
		self.assertFalse(frappe.db.exists("URY Menu", MENU))


class TestImages(RolledBack):
	def test_an_image_of_the_folder_is_attached_to_the_dish_once(self):
		png = (
			b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
			b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x9a\xa0\xa0\x00\x00\x00\x00IEND\xaeB`\x82"
		)
		data = pack(menu=rows(dish(TUNA, COURSE, "食品", KITCHEN_SUSHI, 1000, image="maguro.png")))
		# the rolled-back transaction does not take the file off the disk of the site
		self.addCleanup(lambda: [os.remove(p) for p in (frappe.get_site_path("public", "files", "maguro.png"),) if os.path.exists(p)])
		with tempfile.TemporaryDirectory() as folder:
			os.makedirs(os.path.join(folder, "images"))
			with open(os.path.join(folder, "images", "maguro.png"), "wb") as f:
				f.write(png)
			first = importer.apply_menu(data, folder=folder)
			self.assertEqual(first.errors, [])
			url = frappe.db.get_value("Item", TUNA, "image")
			self.assertTrue(url)
			self.assertEqual(frappe.db.count("File", {"attached_to_doctype": "Item", "attached_to_name": TUNA}), 1)
			second = importer.plan_menu(data, folder=folder)
			self.assertEqual({a.verb for a in second.actions}, {"same"})
			importer.apply_menu(data, folder=folder)
			self.assertEqual(frappe.db.count("File", {"attached_to_doctype": "Item", "attached_to_name": TUNA}), 1)


class TestFromTheExcelFile(RolledBack):
	"""The whole way: the template filled in Excel, read, planned, applied."""

	def test_a_filled_template_is_imported(self):
		from openpyxl import load_workbook

		from ury.setup.datapack import reader, schema, template

		with tempfile.TemporaryDirectory() as folder:
			path = os.path.join(folder, "pack.xlsx")
			template.build_template(path)
			book = load_workbook(path)

			def fill(key, *table):
				ws = book[schema.sheet(key).title]
				for r, values in enumerate(table):
					for c, value in enumerate(values):
						ws.cell(5 + r, c + 1).value = value

			fill("shop", [BRANCH, RESTAURANT, MENU])
			fill("kitchens", [KITCHEN_SUSHI])
			fill("courses", [COURSE, 1, "握寿司", "니기리", "Nigiri"])
			fill("menu", [TUNA, COURSE, "食品", KITCHEN_SUSHI, 1000, None, None, "○", "○", "×", "金枪鱼握寿司"])
			book.save(path)

			data, errors = reader.read_pack(path)
			self.assertEqual(errors, [])
			result = importer.apply_menu(data)

		self.assertEqual(result.errors, [])
		self.assertEqual(frappe.db.get_value("Item", TUNA, "item_group"), f"{KITCHEN_SUSHI}（食品）")
		self.assertEqual(rate_of(TUNA), 1000)
		self.assertEqual(frappe.db.get_value("URY Menu Item", {"parent": MENU, "item": TUNA}, "special_dish"), 1)
		again = importer.plan_menu(data)
		self.assertEqual({a.verb for a in again.actions}, {"same"})
