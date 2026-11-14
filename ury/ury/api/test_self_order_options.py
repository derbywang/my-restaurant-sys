"""Variants and toppings for the guests of the ordering page (2026-11-15; docs/design/self-order-options.md).

A variant (「にぎり（並）」 / 「にぎり（上）」) and a topping (「大盛り」) are dishes of their own (Item), linked from the
dish (`POS Item Variants`, `Item Add On`). The guests are shown one card for a group of variants (the base, with the
lowest price and a 「〜」), no card for a topping, and in the dialog of the dish the grades and the toppings with the
price with the tax. The server lets a guest order a topping of a dish that the guests are shown. Run on the test site
(a trial site first)."""

import frappe

from ury.setup.names import unit_of_measure
from ury.setup.test_site import ALCOHOL_GROUP, ALCOHOL_ITEM, FOOD_COURSE, FOOD_GROUP, FOOD_ITEM, MENU, TABLES
from ury.ury.api import self_ordering
from ury.ury.api.self_ordering import (
	add_customer_items,
	get_customer_menu,
	get_customer_order,
	get_customer_product,
	preview_customer_cart,
	set_session_language,
)
from ury.ury.api.test_ordering_language import add_translation
from ury.ury.api.test_self_ordering_table import PROFILE, TABLE, SelfOrderingCase

PLAIN = "OPテスト玉子"
UP = "OPテスト寿司（上）"
SPECIAL = "OPテスト寿司（特上）"
BIG = f"{FOOD_ITEM}・大盛り"
UP_BIG = f"{UP}・大盛り"
ICE = f"{ALCOHOL_ITEM}・氷"
ALL_NEW = (PLAIN, UP, SPECIAL, BIG, UP_BIG, ICE)


class OptionsCase(SelfOrderingCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(self._remove_options)
		self._remove_options()
		self._make_options()
		self.staff_open()
		self.session = self.scan()

	# the options are made on the test site's menu (committed, like the profile of the base class) and taken away again

	def _remove_options(self):
		frappe.db.rollback()
		frappe.db.delete("POS Item Variants", {"parent": ("in", (FOOD_ITEM, ALCOHOL_ITEM) + ALL_NEW)})
		frappe.db.delete("Item Add On", {"parent": ("in", (FOOD_ITEM, ALCOHOL_ITEM) + ALL_NEW)})
		frappe.db.delete("URY Menu Item", {"parent": MENU, "item": ("in", ALL_NEW)})
		frappe.db.delete("URY Translation Row", {"parent": ("in", (FOOD_ITEM, BIG, UP) + ALL_NEW)})
		for code in ALL_NEW:
			frappe.db.delete("Item Price", {"item_code": code})
			if frappe.db.exists("Item", code):
				frappe.delete_doc("Item", code, force=True, ignore_permissions=True)
		frappe.db.commit()

	def _item(self, code, group, price):
		frappe.get_doc(
			{
				"doctype": "Item", "item_code": code, "item_name": code, "item_group": group, "stock_uom": unit_of_measure("Unit") or "Unit",
				"is_stock_item": 0, "is_sales_item": 1, "standard_rate": price,
			}
		).insert(ignore_permissions=True)

	def _make_options(self):
		rows = {
			PLAIN: (FOOD_GROUP, 200, 1),
			UP: (FOOD_GROUP, 1650, 1),
			SPECIAL: (FOOD_GROUP, 2200, 0),  # a grade for the staff only
			BIG: (FOOD_GROUP, 100, 0),
			UP_BIG: (FOOD_GROUP, 150, 0),
			ICE: (ALCOHOL_GROUP, 50, 0),
		}
		menu = frappe.get_doc("URY Menu", MENU)
		for code, (group, price, self_order) in rows.items():
			self._item(code, group, price)
			menu.append("items", {"item": code, "item_name": code, "rate": price, "course": FOOD_COURSE, "self_order_allowed": self_order})
		menu.save(ignore_permissions=True)
		self.link(FOOD_ITEM, "custom_pos_item_variants", [UP, SPECIAL])
		self.link(UP, "custom_pos_item_variants", [FOOD_ITEM, SPECIAL])
		self.link(SPECIAL, "custom_pos_item_variants", [FOOD_ITEM, UP])
		self.link(FOOD_ITEM, "custom_pos_add_on_items", [BIG])
		self.link(UP, "custom_pos_add_on_items", [UP_BIG])
		self.link(ALCOHOL_ITEM, "custom_pos_add_on_items", [ICE])
		frappe.db.commit()

	def link(self, item, field, targets):
		doc = frappe.get_doc("Item", item)
		for target in targets:
			doc.append(field, {"item": target})
		doc.save(ignore_permissions=True)

	def grid(self):
		return {row["item"]: row for row in get_customer_menu(self.session)["items"]}

	def hide(self, code):
		"""「セルフオーダー可」 off for a dish of the menu, put back when the test is over (the menu is the site's)."""
		original = frappe.db.get_value("URY Menu Item", {"parent": MENU, "item": code}, "self_order_allowed")

		def put_back():
			frappe.db.rollback()
			frappe.db.set_value("URY Menu Item", {"parent": MENU, "item": code}, "self_order_allowed", original)
			frappe.db.commit()

		self.addCleanup(put_back)
		frappe.db.set_value("URY Menu Item", {"parent": MENU, "item": code}, "self_order_allowed", 0)
		frappe.db.commit()

	def refused(self, call, *args, **kwargs):
		frappe.local.message_log = []
		with self.assertRaises((frappe.ValidationError, frappe.DoesNotExistError, frappe.PermissionError)):
			call(*args, **kwargs)


class TestTheGrid(OptionsCase):
	def test_a_dish_with_options_says_so_and_a_plain_dish_does_not(self):
		grid = self.grid()
		self.assertTrue(grid[FOOD_ITEM]["has_options"])
		self.assertTrue(grid[ALCOHOL_ITEM]["has_options"])
		self.assertFalse(grid[PLAIN]["has_options"])

	def test_a_topping_has_no_card(self):
		grid = self.grid()
		for code in (BIG, UP_BIG, ICE):
			self.assertNotIn(code, grid)

	def test_a_group_of_variants_has_one_card_the_base(self):
		grid = self.grid()
		self.assertIn(FOOD_ITEM, grid)
		self.assertNotIn(UP, grid)
		self.assertNotIn(SPECIAL, grid)

	def test_the_card_of_a_group_shows_the_lowest_price_with_the_tax_and_a_from_mark(self):
		row = self.grid()[FOOD_ITEM]
		self.assertEqual(row["price_incl_tax"], 1100)  # the base, 1000 + 10% (dine in)
		self.assertTrue(row["price_from"])

	def test_a_dish_without_other_prices_has_no_from_mark(self):
		self.assertFalse(self.grid()[PLAIN].get("price_from"))
		self.assertFalse(self.grid()[ALCOHOL_ITEM].get("price_from"))

	def test_the_base_is_the_first_of_the_group_on_the_menu_even_when_the_name_sorts_later(self):
		# the menu is listed by name; the base is the dish that was put on the menu first
		order = [r.item for r in frappe.get_all("URY Menu Item", filters={"parent": MENU, "item": ("in", (FOOD_ITEM, UP))}, fields=["item"], order_by="idx")]
		self.assertEqual(order[0], FOOD_ITEM)
		self.assertIn(FOOD_ITEM, self.grid())

	def test_when_the_base_is_not_for_the_guests_the_next_grade_has_the_card(self):
		self.hide(FOOD_ITEM)
		grid = self.grid()
		self.assertNotIn(FOOD_ITEM, grid)
		self.assertIn(UP, grid)

	def test_the_other_dishes_of_the_menu_are_still_there(self):
		self.assertIn(PLAIN, self.grid())


class TestTheDialog(OptionsCase):
	def product(self, item=FOOD_ITEM):
		return get_customer_product(self.session, item)

	def test_the_grades_are_the_group_with_the_price_with_the_tax(self):
		grades = {g["item_code"]: g for g in self.product()["variants"]}
		self.assertEqual(set(grades), {FOOD_ITEM, UP})  # the grade for the staff only is not offered
		self.assertEqual(grades[FOOD_ITEM]["price_incl_tax"], 1100)
		self.assertEqual(grades[UP]["price_incl_tax"], 1815)

	def test_the_dialog_of_a_grade_is_the_same_as_the_one_of_the_base(self):
		self.assertEqual([g["item_code"] for g in self.product(UP)["variants"]], [g["item_code"] for g in self.product(FOOD_ITEM)["variants"]])

	def test_each_grade_has_its_own_toppings_with_the_price_with_the_tax(self):
		grades = {g["item_code"]: g for g in self.product()["variants"]}
		self.assertEqual([a["item_code"] for a in grades[FOOD_ITEM]["addons"]], [BIG])
		self.assertEqual(grades[FOOD_ITEM]["addons"][0]["price_incl_tax"], 110)
		self.assertEqual([a["item_code"] for a in grades[UP]["addons"]], [UP_BIG])
		self.assertEqual(grades[UP]["addons"][0]["price_incl_tax"], 165)

	def test_a_dish_without_grades_lists_its_toppings(self):
		product = self.product(ALCOHOL_ITEM)
		self.assertEqual(product["variants"], [])
		self.assertEqual([a["item_code"] for a in product["addons"]], [ICE])
		self.assertEqual(product["addons"][0]["price_incl_tax"], 55)

	def test_the_label_of_a_topping_has_no_name_of_the_dish_in_front(self):
		grades = {g["item_code"]: g for g in self.product()["variants"]}
		self.assertEqual(grades[FOOD_ITEM]["addons"][0]["label"], "大盛り")
		self.assertEqual(grades[UP]["addons"][0]["label"], "大盛り")
		self.assertEqual(self.product(ALCOHOL_ITEM)["addons"][0]["label"], "氷")

	def test_the_dish_that_asks_the_age_says_so_for_itself_and_its_toppings(self):
		beer = self.product(ALCOHOL_ITEM)
		self.assertTrue(beer["age_check"])
		self.assertTrue(beer["addons"][0]["age_check"])
		sushi = self.product()
		self.assertFalse(sushi["age_check"])
		self.assertFalse(sushi["variants"][0]["addons"][0]["age_check"])

	def test_the_names_follow_the_language_of_the_session(self):
		add_translation(FOOD_ITEM, "Item", "custom_translations", "zh", "寿司测试")
		add_translation(BIG, "Item", "custom_translations", "zh", "寿司测试・加大")
		set_session_language(self.session, "zh")
		product = self.product()
		self.assertEqual(product["item_name"], "寿司测试")
		base = [g for g in product["variants"] if g["item_code"] == FOOD_ITEM][0]
		self.assertEqual(base["item_name"], "寿司测试")
		self.assertEqual(base["addons"][0]["item_name"], "寿司测试・加大")
		self.assertEqual(base["addons"][0]["label"], "加大")

	def test_a_topping_is_not_a_dish_the_guests_can_open(self):
		self.refused(get_customer_product, self.session, BIG)

	def test_a_dish_that_is_not_on_the_menu_cannot_be_opened(self):
		self.refused(get_customer_product, self.session, "OPない品")

	def test_a_topping_without_a_price_is_not_offered(self):
		frappe.db.delete("Item Price", {"item_code": BIG})
		frappe.db.commit()
		grades = {g["item_code"]: g for g in self.product()["variants"]}
		self.assertEqual(grades[FOOD_ITEM]["addons"], [])


class TestOrdering(OptionsCase):
	def test_a_guest_orders_a_grade_and_its_topping(self):
		order = add_customer_items(self.session, [{"item": UP, "qty": 2}, {"item": UP_BIG, "qty": 2}])
		names = {row["item_code"]: row["qty"] for row in order["items"]}
		self.assertEqual(names, {UP: 2, UP_BIG: 2})
		self.assertEqual(order["grand_total"], round((1650 + 150) * 2 * 1.1))

	def test_the_topping_comes_next_to_its_dish_on_the_bill_and_has_a_kitchen_ticket(self):
		add_customer_items(self.session, [{"item": FOOD_ITEM, "qty": 1}, {"item": BIG, "qty": 1}])
		invoice = get_customer_order(self.session)["invoice"]
		lines = frappe.get_all("POS Invoice Item", filters={"parent": invoice}, fields=["item_code"], order_by="idx")
		self.assertEqual([r.item_code for r in lines], [FOOD_ITEM, BIG])
		tickets = frappe.get_all("URY KOT", filters={"invoice": invoice}, pluck="name")
		self.assertEqual(
			set(frappe.get_all("URY KOT Items", filters={"parent": ("in", tickets)}, pluck="item_name")), {FOOD_ITEM, BIG}
		)

	def test_a_topping_of_a_dish_the_guests_are_not_shown_is_refused(self):
		self.hide(FOOD_ITEM)
		self.hide(UP)
		self.refused(add_customer_items, self.session, [{"item": BIG, "qty": 1}])

	def test_a_topping_of_a_dish_that_is_shown_is_accepted_although_it_has_no_card(self):
		self.assertNotIn(BIG, self.grid())
		order = add_customer_items(self.session, [{"item": BIG, "qty": 1}])
		self.assertEqual([r["item_code"] for r in order["items"]], [BIG])

	def test_a_grade_for_the_staff_only_is_refused(self):
		self.refused(add_customer_items, self.session, [{"item": SPECIAL, "qty": 1}])

	def test_a_dish_that_is_not_on_the_menu_is_still_refused(self):
		self.refused(add_customer_items, self.session, [{"item": "OPない品", "qty": 1}])

	def test_an_alcohol_topping_needs_the_answer_about_the_age(self):
		self.refused(add_customer_items, self.session, [{"item": ICE, "qty": 1}])
		self.assertEqual(frappe.db.get_value("URY Ordering Session", {"ordering_profile": PROFILE}, "age_confirmed") or 0, 0)
		order = add_customer_items(self.session, [{"item": ICE, "qty": 1}], age_confirmed=1)
		self.assertEqual([r["item_code"] for r in order["items"]], [ICE])

	def test_the_preview_counts_the_toppings(self):
		preview = preview_customer_cart(self.session, [{"item": FOOD_ITEM, "qty": 1}, {"item": BIG, "qty": 1}])
		self.assertEqual(preview["rounded_total"], round((1000 + 100) * 1.1))


class TestTheTaxOfTheOptions(OptionsCase):
	def prices(self, order_type):
		profile = frappe.get_doc("URY Self Ordering Profile", PROFILE)
		with self_ordering._elevated():
			return self_ordering._prices_incl_tax([BIG, UP_BIG, ICE], profile, order_type)

	def test_to_go_a_topping_of_food_is_8_percent_and_of_alcohol_10(self):
		prices = self.prices("Take Away")
		self.assertEqual(prices[BIG], 108)
		self.assertEqual(prices[UP_BIG], 162)
		self.assertEqual(prices[ICE], 55)

	def test_eating_in_everything_is_10_percent(self):
		prices = self.prices("Dine In")
		self.assertEqual(prices[BIG], 110)
		self.assertEqual(prices[ICE], 55)
