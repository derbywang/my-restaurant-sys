"""An order whose rows were made by several rounds of the guests (self ordering: a new row each time) is saved by the register
as the cart line the register shows: ONE line for the dish (the cart merges the rows, `mergeCartLines`). The server takes the
cart as it is: the rows are replaced by the lines, the kitchen is told the difference by dish and note (`compare_two_array`),
the note check counts by dish and note. This guards that way of saving (2026-11-10). Run on the test site only."""

import frappe

from ury.setup.test_site import CASHIER, FOOD_ITEM, TABLES, URYFlowTestCase, open_pos, place_order


class TestSavingAMergedLine(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		open_pos(CASHIER)
		self.order = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])
		# the guests' second round: a new row of the same dish
		doc = frappe.get_doc("POS Invoice", self.order)
		row = doc.items[0].as_dict()
		for key in ("name", "idx", "creation", "modified", "owner", "modified_by", "parent", "parentfield", "parenttype", "docstatus"):
			row.pop(key, None)
		row["qty"] = 2
		doc.append("items", row)
		doc.save()
		frappe.db.commit()

	def _rows(self):
		return [(row.item_code, row.qty, row.get("comment") or "") for row in frappe.get_doc("POS Invoice", self.order).items]

	def _tickets(self, types, field="quantity"):
		"""[(dish, number)] of the tickets of these types of the order: `quantity` of a ticket that sends, `cancelled_qty` of one that takes back."""
		types = (types,) if isinstance(types, str) else tuple(types)
		return [
			(row.item, int(row.get(field)))
			for ticket in frappe.get_all("URY KOT", filters={"invoice": self.order, "type": ["in", types]}, pluck="name")
			for row in frappe.get_all("URY KOT Items", filters={"parent": ticket}, fields=["item", field])
			if row.get(field)
		]

	def _save(self, qty):
		return place_order(CASHIER, [(FOOD_ITEM, qty)], table=TABLES[0], invoice=self.order)

	def test_the_two_rows_become_one_row_and_a_bigger_quantity_is_told_to_the_kitchen_as_the_difference(self):
		self.assertEqual(self._rows(), [(FOOD_ITEM, 1, ""), (FOOD_ITEM, 2, "")])
		self._save(5)  # the line of 3 was changed to 5
		self.assertEqual(self._rows(), [(FOOD_ITEM, 5, "")])
		self.assertEqual(self._tickets("Order Modified"), [(FOOD_ITEM, 2)])

	def test_saving_the_merged_line_as_it_is_tells_the_kitchen_nothing(self):
		before = frappe.db.count("URY KOT", {"invoice": self.order})
		self._save(3)
		self.assertEqual(self._rows(), [(FOOD_ITEM, 3, "")])
		self.assertEqual(frappe.db.count("URY KOT", {"invoice": self.order}), before)

	def test_a_smaller_quantity_is_a_cancel_ticket_for_the_difference(self):
		self._save(2)  # one dish taken back (the cashier may: the POS Profile allows it)
		self.assertEqual(self._rows(), [(FOOD_ITEM, 2, "")])
		self.assertEqual(self._tickets(("Cancelled", "Partially cancelled"), "cancelled_qty"), [(FOOD_ITEM, 1)])
