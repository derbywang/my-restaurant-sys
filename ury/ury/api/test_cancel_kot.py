"""The kitchen tickets of a cancelled or changed order (`cancel_kot`, `kot_execute`).

A cancel ticket must list what the order had, once: an order with two Sake lines (1 each) used to
give a ticket with four. Run on the test site only.
"""

import frappe

from ury.setup.test_site import (
	ALCOHOL_ITEM,
	POS_PROFILE,
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


class TestTheQuantitiesOfACancelTicket(URYFlowTestCase):
	"""A cancel ticket row says what the order had of that dish WITH THAT NOTE before the change (`quantity`, the kitchen screen
	shows it as 「変更前」) and how many are taken back (`cancelled_qty`); the screen shows `quantity - cancelled_qty` as the quantity
	that is left. They were taken from 'the next line of the dish' whatever its note: taking back the 2 辛さ控えめ of a Burger that
	had also 4 without a note showed 「Burger 2 [変更前 4]」, which reads as 'the spicy ones go from 4 to 2' (2026-11-13).
	Run on the test site only."""

	NOTE = "辛さ控えめ"

	def setUp(self):
		super().setUp()
		open_pos(CASHIER)
		original = frappe.db.get_value("POS Profile", POS_PROFILE, "remove_items")
		self.addCleanup(self._set_remove_items, original)
		self._set_remove_items(1)

	def _set_remove_items(self, value):
		frappe.db.set_value("POS Profile", POS_PROFILE, "remove_items", value)
		frappe.db.commit()
		frappe.clear_document_cache("POS Profile", POS_PROFILE)

	def _order(self, items):
		invoice = place_order(CASHIER, [items[0]], order_type="Take Away")
		if len(items) > 1:
			place_order(CASHIER, items, order_type="Take Away", invoice=invoice)
		return invoice

	def _change(self, invoice, items):
		"""Change the order; the rows [(quantity, cancelled_qty, note)] of the cancel tickets made by this change."""
		before = set(frappe.get_all("URY KOT", filters={"invoice": invoice}, pluck="name"))
		place_order(CASHIER, items, order_type="Take Away", invoice=invoice)
		return self._cancel_rows(invoice, before)

	def _cancel_rows(self, invoice, before):
		rows = []
		for ticket in frappe.get_all(
			"URY KOT",
			filters={"invoice": invoice, "type": ["in", ["Cancelled", "Partially cancelled"]], "name": ["not in", list(before) or [""]]},
			pluck="name",
			order_by="creation asc, name asc",
		):
			for row in frappe.get_all("URY KOT Items", filters={"parent": ticket}, fields=["item", "quantity", "cancelled_qty", "comments"], order_by="idx asc"):
				rows.append((int(row.quantity), int(row.cancelled_qty), row.comments or ""))
		return rows

	def test_taking_back_the_line_with_a_note_shows_that_note_going_from_2_to_0(self):
		invoice = self._order([(FOOD_ITEM, 4), (FOOD_ITEM, 2, self.NOTE)])
		rows = self._change(invoice, [(FOOD_ITEM, 4)])
		self.assertEqual(rows, [(2, 2, self.NOTE)])  # before 2, 2 taken back: the screen shows 0 left
		self.assertEqual(rows[0][0] - rows[0][1], 0)

	def test_fewer_of_the_line_with_a_note_shows_that_note_going_from_3_to_1(self):
		invoice = self._order([(FOOD_ITEM, 4), (FOOD_ITEM, 3, self.NOTE)])
		self.assertEqual(self._change(invoice, [(FOOD_ITEM, 4), (FOOD_ITEM, 1, self.NOTE)]), [(3, 2, self.NOTE)])

	def test_fewer_of_the_line_without_a_note_shows_that_line_going_from_4_to_3(self):
		invoice = self._order([(FOOD_ITEM, 4), (FOOD_ITEM, 2, self.NOTE)])
		self.assertEqual(self._change(invoice, [(FOOD_ITEM, 3), (FOOD_ITEM, 2, self.NOTE)]), [(4, 1, "")])

	def test_a_dish_that_is_gone_takes_back_each_note_with_its_own_quantity(self):
		invoice = self._order([(FOOD_ITEM, 4), (FOOD_ITEM, 2, self.NOTE), (ALCOHOL_ITEM, 1)])
		rows = self._change(invoice, [(ALCOHOL_ITEM, 1)])
		self.assertEqual(sorted(rows), [(2, 2, self.NOTE), (4, 4, "")])

	def test_two_saved_rows_of_the_same_dish_and_note_count_together_as_what_there_was(self):
		"""The rounds of the guests are two rows of the order (1 and 2): the line of the register had 3."""
		invoice = place_order(CASHIER, [(FOOD_ITEM, 1)], order_type="Take Away")
		doc = frappe.get_doc("POS Invoice", invoice)
		row = doc.items[0].as_dict()
		for key in ("name", "idx", "creation", "modified", "owner", "modified_by", "parent", "parentfield", "parenttype", "docstatus"):
			row.pop(key, None)
		row["qty"] = 2
		doc.append("items", row)
		doc.save()
		frappe.db.commit()
		self.assertEqual(self._change(invoice, [(FOOD_ITEM, 2)]), [(3, 1, "")])

	def test_cancelling_the_whole_order_takes_back_each_note_in_full(self):
		invoice = self._order([(FOOD_ITEM, 4), (FOOD_ITEM, 2, self.NOTE)])
		before = set(frappe.get_all("URY KOT", filters={"invoice": invoice}, pluck="name"))
		with as_user(CASHIER):
			cancel_order(invoice, "test")
		self.assertEqual(sorted(self._cancel_rows(invoice, before)), [(2, 2, self.NOTE), (4, 4, "")])
