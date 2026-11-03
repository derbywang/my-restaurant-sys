"""What the kitchen is told when an order changes (`kot_execute`: compare_two_array / get_removed_items).

A dish can be on two lines of an order (a captain added it in two rounds, a note differs). The
kitchen must still be sent exactly the difference of the totals: the second Sake line used to send
nothing, and removing one of two Sake lines used to cancel nothing. Run on the test site only.
"""

import copy

import frappe

from ury.setup.test_site import (
	ALCOHOL_ITEM,
	CASHIER,
	FOOD_ITEM,
	POS_PROFILE,
	URYFlowTestCase,
	URYTestCase,
	open_pos,
	place_order,
)
from ury.ury.api.ury_kot_generate import compare_two_array, get_removed_items


def line(item, qty, comments=""):
	return {"item_code": item, "item_name": item, "qty": qty, "comments": comments}


class TestCompareTwoArrays(URYTestCase):
	"""compare_two_array(current, previous): the items to send (qty > 0) or take back (qty < 0)."""

	def diff(self, current, previous):
		return [(row["item_code"], row["qty"]) for row in compare_two_array(current, previous)]

	def test_nothing_changed(self):
		self.assertEqual(self.diff([line("Sake", 1)], [line("Sake", 1)]), [])
		self.assertEqual(self.diff([line("Sake", 1), line("Sake", 1)], [line("Sake", 1), line("Sake", 1)]), [])

	def test_a_new_dish(self):
		self.assertEqual(self.diff([line("Sake", 2)], []), [("Sake", 2)])

	def test_a_new_dish_on_two_lines_is_sent_per_line(self):
		self.assertEqual(self.diff([line("Sake", 1), line("Sake", 1)], []), [("Sake", 1), ("Sake", 1)])

	def test_a_second_line_of_a_dish_that_is_already_there_is_sent(self):
		self.assertEqual(self.diff([line("Sake", 1), line("Sake", 1)], [line("Sake", 1)]), [("Sake", 1)])

	def test_removing_one_of_two_lines_takes_back_one(self):
		self.assertEqual(self.diff([line("Sake", 1)], [line("Sake", 1), line("Sake", 1)]), [("Sake", -1)])

	def test_two_lines_that_make_the_same_total_change_nothing(self):
		self.assertEqual(self.diff([line("Sake", 1), line("Sake", 1)], [line("Sake", 2)]), [])
		self.assertEqual(self.diff([line("Sake", 2)], [line("Sake", 1), line("Sake", 1)]), [])

	def test_a_higher_quantity_sends_the_difference(self):
		self.assertEqual(self.diff([line("Sake", 3)], [line("Sake", 1)]), [("Sake", 2)])

	def test_a_lower_quantity_takes_back_the_difference(self):
		self.assertEqual(self.diff([line("Sake", 2)], [line("Sake", 3)]), [("Sake", -1)])

	def test_the_difference_is_of_the_total_of_all_lines(self):
		current = [line("Sake", 2), line("Sake", 2)]
		previous = [line("Sake", 1), line("Sake", 1), line("Sake", 1)]
		self.assertEqual(self.diff(current, previous), [("Sake", 1)])

	def test_the_new_line_carries_its_own_note(self):
		current = [line("Sake", 1, ""), line("Sake", 1, "cold")]
		rows = compare_two_array(current, [line("Sake", 1)])
		self.assertEqual([(row["qty"], row["comments"]) for row in rows], [(1, "cold")])

	def test_each_dish_is_compared_on_its_own_and_the_order_is_kept(self):
		current = [line("Pizza", 1), line("Sake", 2), line("Beer", 1)]
		previous = [line("Sake", 1), line("Pizza", 1)]
		self.assertEqual(self.diff(current, previous), [("Sake", 1), ("Beer", 1)])

	def test_a_dish_that_is_gone_is_not_in_the_difference(self):
		# whole dishes that were removed come from get_removed_items
		self.assertEqual(self.diff([line("Pizza", 1)], [line("Pizza", 1), line("Sake", 2)]), [])
		self.assertEqual(
			[(row["item_code"], row["qty"]) for row in get_removed_items([line("Pizza", 1), line("Sake", 2)], [line("Pizza", 1)])],
			[("Sake", 2)],
		)

	def test_the_arguments_are_left_alone(self):
		current = [line("Sake", 3), line("Sake", 1)]
		previous = [line("Sake", 1)]
		before = copy.deepcopy((current, previous))
		compare_two_array(current, previous)
		self.assertEqual((current, previous), before)


class TestTicketsOfAChangedOrder(URYFlowTestCase):
	"""The tickets the kitchen gets when an order with a dish on two lines is changed."""

	def setUp(self):
		super().setUp()
		open_pos(CASHIER)
		original = frappe.db.get_value("POS Profile", POS_PROFILE, "remove_items")
		self.addCleanup(self._set_remove_items, original)
		self._set_remove_items(1)  # reducing an order needs this switch of the POS Profile

	def _set_remove_items(self, value):
		frappe.db.set_value("POS Profile", POS_PROFILE, "remove_items", value)
		frappe.db.commit()
		frappe.clear_document_cache("POS Profile", POS_PROFILE)

	def _order(self, items):
		return place_order(CASHIER, items, order_type="Take Away")

	def _change(self, name, items):
		"""Change the order and return (sent, taken_back): {item: quantity} of the new tickets."""
		before = set(frappe.get_all("URY KOT", filters={"invoice": name}, pluck="name"))
		place_order(CASHIER, items, order_type="Take Away", invoice=name)
		sent, taken_back = {}, {}
		for ticket in frappe.get_all("URY KOT", filters={"invoice": name}, fields=["name", "type"]):
			if ticket.name in before:
				continue
			for row in frappe.get_all("URY KOT Items", filters={"parent": ticket.name}, fields=["item", "quantity", "cancelled_qty"]):
				if ticket.type in ("New Order", "Order Modified"):
					sent[row.item] = sent.get(row.item, 0) + int(row.quantity)
				else:
					taken_back[row.item] = taken_back.get(row.item, 0) + int(row.cancelled_qty or 0)
		return sent, taken_back

	def test_a_second_line_of_a_dish_reaches_the_kitchen(self):
		name = self._order([(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)])
		sent, taken_back = self._change(name, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1), (ALCOHOL_ITEM, 1)])
		self.assertEqual(sent.get(ALCOHOL_ITEM), 1)
		self.assertNotIn(FOOD_ITEM, sent)
		self.assertEqual(taken_back, {})

	def test_removing_one_of_two_lines_is_taken_back_in_the_kitchen(self):
		name = self._order([(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1), (ALCOHOL_ITEM, 1)])
		sent, taken_back = self._change(name, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)])
		self.assertEqual(taken_back.get(ALCOHOL_ITEM), 1)
		self.assertEqual(sent, {})

	def test_two_lines_made_one_line_of_the_same_total_tell_the_kitchen_nothing(self):
		name = self._order([(ALCOHOL_ITEM, 1), (ALCOHOL_ITEM, 1)])
		sent, taken_back = self._change(name, [(ALCOHOL_ITEM, 2)])
		self.assertEqual((sent, taken_back), ({}, {}))

	def test_removing_both_lines_takes_back_both(self):
		name = self._order([(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1), (ALCOHOL_ITEM, 1)])
		sent, taken_back = self._change(name, [(FOOD_ITEM, 1)])
		self.assertEqual(taken_back.get(ALCOHOL_ITEM), 2)
		self.assertEqual(sent, {})

	def test_a_higher_and_a_lower_quantity_still_work(self):
		name = self._order([(ALCOHOL_ITEM, 2)])
		sent, taken_back = self._change(name, [(ALCOHOL_ITEM, 3)])
		self.assertEqual((sent, taken_back), ({ALCOHOL_ITEM: 1}, {}))
		sent, taken_back = self._change(name, [(ALCOHOL_ITEM, 1)])
		self.assertEqual(sent, {})
		self.assertEqual(taken_back.get(ALCOHOL_ITEM), 2)
