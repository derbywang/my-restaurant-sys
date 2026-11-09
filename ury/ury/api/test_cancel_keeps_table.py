"""Cancelling a bill does not free a table that other guests are using (2026-11-10, found while checking the table cards).

Printing a bill frees the table (the guests are at the register), so the next guests may be seated at once and get a new order.
Cancelling the first guests' bill used to free the table all the same: the card said 空席 and the self ordering of the table
was closed while the next guests sat there. Paying already looks at the other open orders (`_free_tables_if_no_open_invoices`);
cancelling now does too. Run on the test site only."""

import frappe

from ury.setup.test_site import (
	CASHIER,
	CAPTAIN,
	FOOD_ITEM,
	TABLES,
	URYFlowTestCase,
	as_user,
	open_pos,
	place_order,
	print_bill,
)
from ury.ury.doctype.ury_order.ury_order import cancel_order

TABLE = TABLES[0]


class TestCancelKeepsTheTable(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		open_pos(CASHIER)

	def _cancel(self, invoice):
		with as_user(CASHIER):
			cancel_order(invoice, "test")

	def _table(self):
		return frappe.db.get_value("URY Table", TABLE, ["occupied", "self_order_open"], as_dict=True)

	def _open_self_ordering(self):
		frappe.db.set_value("URY Table", TABLE, {"self_order_open": 1})
		frappe.db.commit()

	def _printed_first_guests_then_next_guests(self):
		first = place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLE)
		print_bill(first, CASHIER)  # the guests are at the register: the table is free
		self.assertEqual(self._table().occupied, 0)
		second = place_order(CAPTAIN, [(FOOD_ITEM, 2)], table=TABLE)  # the next guests: a new order
		self.assertNotEqual(first, second)
		self.assertEqual(self._table().occupied, 1)
		return first, second

	def test_cancelling_the_printed_bill_of_the_first_guests_keeps_the_table_of_the_next_guests(self):
		first, second = self._printed_first_guests_then_next_guests()
		self._open_self_ordering()
		self._cancel(first)
		table = self._table()
		self.assertEqual(table.occupied, 1)
		self.assertEqual(table.self_order_open, 1)  # and their self ordering is not closed
		self.assertEqual(frappe.db.get_value("POS Invoice", second, "docstatus"), 0)

	def test_cancelling_the_order_of_the_guests_that_sit_there_frees_the_table_when_nobody_else_does(self):
		invoice = place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLE)
		self._open_self_ordering()
		self._cancel(invoice)
		table = self._table()
		self.assertEqual((table.occupied, table.self_order_open), (0, 0))

	def test_cancelling_leaves_the_table_free_when_only_printed_bills_remain(self):
		"""Another printed bill is guests at the register, not guests at the table."""
		first = place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLE)
		print_bill(first, CASHIER)
		second = place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLE)
		print_bill(second, CASHIER)
		self._open_self_ordering()
		self._cancel(first)
		table = self._table()
		self.assertEqual((table.occupied, table.self_order_open), (0, 0))
