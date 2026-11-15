"""The menu the register and the captain's screen load says which items are toppings (2026-11-15).

A topping is an item that another item lists in `Item Add On` (the dialog of the dish offers it). The register and the
captain's screen do not give it a card, a search result or a count, but the dialog of the dish needs its name and price, so
it stays in the list with `is_addon` set. Everything runs in a rolled-back savepoint of the test site."""

import frappe

from ury.setup.test_site import ALCOHOL_ITEM, BRANCH, FOOD_ITEM, URYTestCase
from ury.ury_pos.api import resolve_restaurant_menu


class TestMenuToppings(URYTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.savepoint("menu_toppings")
		self.addCleanup(frappe.db.rollback, save_point="menu_toppings")

	def menu(self):
		return {row["item"]: row for row in resolve_restaurant_menu(BRANCH, None, None, True)["items"]}

	def link(self, item, target):
		doc = frappe.get_doc("Item", item)
		doc.append("custom_pos_add_on_items", {"item": target})
		doc.save(ignore_permissions=True)

	def test_without_links_nothing_is_a_topping(self):
		menu = self.menu()
		self.assertIn(FOOD_ITEM, menu)
		self.assertFalse(any(row["is_addon"] for row in menu.values()))

	def test_an_item_listed_as_a_topping_is_marked_and_stays_in_the_list(self):
		self.link(FOOD_ITEM, ALCOHOL_ITEM)
		menu = self.menu()
		self.assertEqual(menu[ALCOHOL_ITEM]["is_addon"], 1)
		self.assertEqual(menu[ALCOHOL_ITEM]["rate"], frappe.db.get_value("URY Menu Item", {"item": ALCOHOL_ITEM}, "rate"))
		self.assertEqual(menu[FOOD_ITEM]["is_addon"], 0)

	def test_a_variant_is_not_a_topping(self):
		doc = frappe.get_doc("Item", FOOD_ITEM)
		doc.append("custom_pos_item_variants", {"item": ALCOHOL_ITEM})
		doc.save(ignore_permissions=True)
		self.assertEqual(self.menu()[ALCOHOL_ITEM]["is_addon"], 0)
