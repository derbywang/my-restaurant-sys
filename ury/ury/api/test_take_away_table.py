"""A table is in use only for a dine in order (or when it is a take away table).

An order that is not dine in used to mark the table it was sent with as in use, so a take away
order that still carried the table picked earlier kept that table busy. Run on the test site only.
"""

import frappe

from ury.setup.test_site import (
	ALCOHOL_ITEM,
	CASHIER,
	FOOD_ITEM,
	TABLES,
	URYFlowTestCase,
	open_pos,
	place_order,
)


class TestTableOccupancy(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		open_pos(CASHIER)

	def _occupied(self, table):
		return frappe.db.get_value("URY Table", table, "occupied")

	def test_a_dine_in_order_occupies_its_table(self):
		place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0], order_type="Dine In")
		self.assertEqual(self._occupied(TABLES[0]), 1)

	def test_a_take_away_order_with_an_ordinary_table_does_not(self):
		self.assertEqual(self._occupied(TABLES[0]), 0)
		place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0], order_type="Take Away")
		self.assertEqual(self._occupied(TABLES[0]), 0)

	def test_nor_does_an_order_of_another_type(self):
		for table, order_type in ((TABLES[0], "Delivery"), (TABLES[1], "Phone In")):
			place_order(CASHIER, [(FOOD_ITEM, 1)], table=table, order_type=order_type)
			self.assertEqual(self._occupied(table), 0, order_type)

	def test_a_take_away_table_is_occupied_by_its_take_away_order(self):
		frappe.db.set_value("URY Table", TABLES[2], "is_take_away", 1)
		frappe.db.commit()
		self.addCleanup(self._release_take_away_table)
		place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[2], order_type="Take Away")
		self.assertEqual(self._occupied(TABLES[2]), 1)

	def _release_take_away_table(self):
		frappe.db.set_value("URY Table", TABLES[2], {"is_take_away": 0, "occupied": 0})
		frappe.db.commit()

	def test_updating_a_take_away_order_still_leaves_the_table_free(self):
		name = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0], order_type="Take Away")
		place_order(
			CASHIER, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)], table=TABLES[0], order_type="Take Away", invoice=name
		)
		self.assertEqual(self._occupied(TABLES[0]), 0)
