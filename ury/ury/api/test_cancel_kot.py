"""The kitchen tickets of a cancelled or changed order (`cancel_kot`, `kot_execute`).

A cancel ticket must list what the order had, once: an order with two Sake lines (1 each) used to
give a ticket with four. Run on the test site only.
"""

import frappe

from ury.setup.test_site import (
	ALCOHOL_ITEM,
	CASHIER,
	FOOD_ITEM,
	URYFlowTestCase,
	as_user,
	open_pos,
	place_order,
)
from ury.ury.api.ury_kot_generate import compare_two_array
from ury.ury.doctype.ury_order.ury_order import cancel_order


class TestCancelKot(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		open_pos(CASHIER)

	def _cancel(self, invoice):
		with as_user(CASHIER):
			cancel_order(invoice, "test")

	def _per_item(self, invoice, ticket_type, field):
		"""{item: total of `field`} over the tickets of this type that the invoice has."""
		totals = {}
		for ticket in frappe.get_all("URY KOT", filters={"invoice": invoice, "type": ticket_type}, pluck="name"):
			for row in frappe.get_all("URY KOT Items", filters={"parent": ticket}, fields=["item", field]):
				totals[row.item] = totals.get(row.item, 0) + int(row.get(field))
		return totals

	def _assert_cancelled_what_was_ordered(self, invoice):
		"""The cancel tickets take back exactly what the kitchen was sent, item by item."""
		sent = self._per_item(invoice, "New Order", "quantity")
		self.assertTrue(sent)
		self.assertEqual(self._per_item(invoice, "Cancelled", "cancelled_qty"), sent)

	def test_an_order_of_single_lines_is_cancelled_line_for_line(self):
		name = place_order(CASHIER, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)], order_type="Take Away")
		self._cancel(name)
		self._assert_cancelled_what_was_ordered(name)

	def test_two_lines_of_the_same_dish_are_cancelled_once_each(self):
		name = place_order(CASHIER, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1), (ALCOHOL_ITEM, 1)], order_type="Take Away")
		self.assertEqual(frappe.db.count("POS Invoice Item", {"parent": name, "item_code": ALCOHOL_ITEM}), 2)
		self._cancel(name)
		self._assert_cancelled_what_was_ordered(name)
		sent = self._per_item(name, "New Order", "quantity")
		if ALCOHOL_ITEM in sent:
			self.assertEqual(sent[ALCOHOL_ITEM], 2)

	def test_a_line_with_a_quantity_is_cancelled_with_that_quantity(self):
		name = place_order(CASHIER, [(ALCOHOL_ITEM, 3)], order_type="Take Away")
		self._cancel(name)
		self._assert_cancelled_what_was_ordered(name)

	def test_the_ticket_of_a_dish_added_later_has_that_dish_only_once(self):
		name = place_order(CASHIER, [(FOOD_ITEM, 1)], order_type="Take Away")
		place_order(
			CASHIER,
			[(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1), (ALCOHOL_ITEM, 1)],
			order_type="Take Away",
			invoice=name,
		)
		added = self._per_item(name, "Order Modified", "quantity")
		self.assertEqual(added.get(ALCOHOL_ITEM, 2), 2)
		self.assertNotIn(FOOD_ITEM, added)


class TestCompareTwoArrays(URYFlowTestCase):
	"""What compare_two_array does with a dish that is on two lines (kept as it is; see ui-todo.md)."""

	def _line(self, item, qty):
		return {"item_code": item, "qty": qty, "item_name": item, "comments": ""}

	def test_a_new_dish_comes_through_per_line(self):
		current = [self._line("Sake", 1), self._line("Sake", 1)]
		self.assertEqual([row["qty"] for row in compare_two_array(current, [])], [1, 1])
