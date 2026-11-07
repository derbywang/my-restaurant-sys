"""A dish whose item group belongs to no production unit never reaches the kitchen: nobody must miss that.

`process_items_for_kot` used to skip such a dish with a plain message and went on: the order was saved with no
kitchen ticket for it (a self-order guest saw nothing at all, the register nothing). Now the register is told on the
kitchen error channels, the staff member who took the order gets the same sentence, and the menu can be checked
for such dishes before and after it is changed. Run on the test site only.
"""

from unittest.mock import patch

import frappe

from ury.setup.test_site import (
	ALCOHOL_GROUP,
	ALCOHOL_ITEM,
	BRANCH,
	CAPTAIN,
	CASHIER,
	FOOD_ITEM,
	MENU,
	PRODUCTION_UNIT,
	TABLES,
	URYFlowTestCase,
	as_user,
	open_pos,
	place_order,
)
from ury.ury.api.kitchen_check import items_without_kitchen, menu_items_without_kitchen
from ury.ury.api.test_self_ordering_table import SelfOrderingCase

CHANNEL = f"kot_error_{BRANCH}_{PRODUCTION_UNIT}"


class NoKitchenForBeer:
	"""The beer's group is taken out of the production unit for the length of a test (put back by the cleanup)."""

	def leave_beer_without_kitchen(self):
		rows = frappe.get_all(
			"URY Production Item Groups", filters={"parent": PRODUCTION_UNIT, "item_group": ALCOHOL_GROUP}, pluck="name"
		)
		self.assertTrue(rows, "the test kitchen makes the beer")
		frappe.db.delete("URY Production Item Groups", {"name": ["in", rows]})
		self.addCleanup(self._put_beer_back)

	def _put_beer_back(self):
		unit = frappe.get_doc("URY Production Unit", PRODUCTION_UNIT)
		if not any(row.item_group == ALCOHOL_GROUP for row in unit.item_groups):
			unit.append("item_groups", {"item_group": ALCOHOL_GROUP})
			unit.save(ignore_permissions=True)
		frappe.db.commit()


def alerts(publish):
	return [c for c in publish.call_args_list if str(c.args[0]).startswith("kot_error_")]


class TestCheckOfTheDishes(NoKitchenForBeer, URYFlowTestCase):
	def test_dishes_of_a_group_without_kitchen_are_found(self):
		self.assertEqual(items_without_kitchen(BRANCH, [FOOD_ITEM, ALCOHOL_ITEM]), [])
		self.leave_beer_without_kitchen()
		self.assertEqual([row["item_code"] for row in items_without_kitchen(BRANCH, [FOOD_ITEM, ALCOHOL_ITEM])], [ALCOHOL_ITEM])

	def test_the_menu_check_lists_them_and_changes_nothing(self):
		self.assertEqual(menu_items_without_kitchen(BRANCH), [])
		self.leave_beer_without_kitchen()
		before = frappe.db.count("URY Production Item Groups")
		rows = menu_items_without_kitchen(BRANCH)
		self.assertEqual([(r["menu"], r["item"], r["item_group"]) for r in rows], [(MENU, ALCOHOL_ITEM, ALCOHOL_GROUP)])
		self.assertEqual(frappe.db.count("URY Production Item Groups"), before)

	def test_a_dish_left_out_of_the_menu_or_switched_off_is_not_listed(self):
		self.leave_beer_without_kitchen()
		row = frappe.db.get_value("URY Menu Item", {"parent": MENU, "item": ALCOHOL_ITEM}, "name")
		frappe.db.set_value("URY Menu Item", row, "disabled", 1)
		self.addCleanup(lambda: frappe.db.set_value("URY Menu Item", row, "disabled", 0))
		self.assertEqual(menu_items_without_kitchen(BRANCH), [])

	def test_saving_the_menu_warns_without_stopping_it(self):
		self.leave_beer_without_kitchen()
		menu = frappe.get_doc("URY Menu", MENU)
		frappe.local.message_log = []
		menu.save(ignore_permissions=True)  # not refused
		messages = " ".join(str(m) for m in frappe.local.message_log)
		self.assertIn(ALCOHOL_ITEM, messages)

	def test_saving_a_menu_that_is_all_right_says_nothing(self):
		menu = frappe.get_doc("URY Menu", MENU)
		frappe.local.message_log = []
		menu.save(ignore_permissions=True)
		self.assertEqual([m for m in frappe.local.message_log if "kitchen" in str(m).lower() or "厨房" in str(m)], [])


class TestOrderOfADishWithoutKitchen(NoKitchenForBeer, URYFlowTestCase):
	def setUp(self):
		super().setUp()
		open_pos(CASHIER)

	def _order(self, user, items, table=TABLES[0]):
		with patch("ury.ury.api.kitchen_check.frappe.publish_realtime") as publish:
			name = place_order(user, items, table=table)
		return name, alerts(publish)

	def test_the_order_is_saved_the_register_is_told_and_the_message_names_the_dish(self):
		self.leave_beer_without_kitchen()
		frappe.local.message_log = []
		name, sent = self._order(CASHIER, [(ALCOHOL_ITEM, 1)])
		self.assertEqual(frappe.db.count("POS Invoice Item", {"parent": name}), 1)
		self.assertEqual(frappe.db.count("URY KOT", {"invoice": name}), 0)
		self.assertEqual([c.args[0] for c in sent], [CHANNEL])
		payload = sent[0].args[1]
		self.assertEqual((payload["kind"], payload["invoice"], payload["table"]), ("no_kitchen", name, TABLES[0]))
		self.assertEqual(payload["items"], [ALCOHOL_ITEM])
		self.assertTrue(sent[0].kwargs.get("after_commit"))
		self.assertIn(ALCOHOL_ITEM, " ".join(str(m) for m in frappe.local.message_log))

	def test_only_the_dish_without_kitchen_is_reported_the_other_gets_its_ticket(self):
		self.leave_beer_without_kitchen()
		name, sent = self._order(CAPTAIN, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)])
		self.assertEqual(sent[0].args[1]["items"], [ALCOHOL_ITEM])
		tickets = frappe.get_all("URY KOT", filters={"invoice": name}, pluck="name")
		self.assertEqual(len(tickets), 1)
		self.assertEqual(frappe.get_all("URY KOT Items", filters={"parent": tickets[0]}, pluck="item"), [FOOD_ITEM])

	def test_an_ordinary_order_tells_nobody(self):
		_name, sent = self._order(CASHIER, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)])
		self.assertEqual(sent, [])

	def test_the_message_is_japanese_for_a_japanese_speaker(self):
		self.leave_beer_without_kitchen()
		previous = frappe.local.lang
		self.addCleanup(lambda: setattr(frappe.local, "lang", previous))
		frappe.clear_cache()  # the translations are cached
		frappe.local.lang = "ja"  # what a staff member whose language is Japanese has during the request
		frappe.local.message_log = []
		self._order(CASHIER, [(ALCOHOL_ITEM, 1)])
		text = " ".join(str(m) for m in frappe.local.message_log)
		self.assertIn("厨房伝票が出ませんでした", text)


class TestSelfOrderOfADishWithoutKitchen(NoKitchenForBeer, SelfOrderingCase):
	def test_the_guest_orders_and_the_register_is_told(self):
		self.leave_beer_without_kitchen()
		self.staff_open()
		session = self.scan()
		with patch("ury.ury.api.kitchen_check.frappe.publish_realtime") as publish:
			order = self.order_item(session, ALCOHOL_ITEM)
		sent = alerts(publish)
		self.assertEqual([c.args[0] for c in sent], [CHANNEL])
		self.assertEqual(sent[0].args[1]["invoice"], order["invoice"])
		self.assertEqual(sent[0].args[1]["items"], [ALCOHOL_ITEM])

	def test_the_guest_is_not_shown_the_message_meant_for_the_staff(self):
		self.leave_beer_without_kitchen()
		self.staff_open()
		session = self.scan()
		frappe.local.message_log = []
		self.order_item(session, ALCOHOL_ITEM)
		texts = " ".join(str(m.get("message", m)) for m in frappe.local.message_log)
		self.assertNotIn("kitchen", texts.lower())
		self.assertNotIn("厨房", texts)

	def order_item(self, session, item):
		from ury.ury.api.self_ordering import add_customer_items

		return add_customer_items(session, [{"item": item, "qty": 1}], age_confirmed=1)
