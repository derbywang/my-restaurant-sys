"""`getPosInvoiceItems`: the rows of the order detail of the order list (「伝票」→「注文明細」). They carry the dish code and the note
of the row, so that the screen can join the rows of the same dish and note and show the note (2026-11-13). Run on the test site only."""

import frappe

from ury.setup.test_site import CASHIER, CAPTAIN, FOOD_ITEM, TABLES, URYFlowTestCase, as_user, open_pos, place_order
from ury.ury_pos.api import getPosInvoiceItems


class TestPosInvoiceItems(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		open_pos(CASHIER)

	def _items(self, invoice):
		with as_user(CASHIER):
			return getPosInvoiceItems(invoice)[0]

	def test_a_row_has_the_dish_code_and_the_note(self):
		invoice = place_order(CAPTAIN, [(FOOD_ITEM, 2, "辛さ控えめ")], table=TABLES[0])
		[row] = self._items(invoice)
		self.assertEqual(row["item_code"], FOOD_ITEM)
		self.assertEqual(row["comment"], "辛さ控えめ")
		self.assertEqual((row["qty"], row["rate"]), (2, 1000))

	def test_a_row_without_a_note_has_an_empty_one(self):
		invoice = place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLES[0])
		[row] = self._items(invoice)
		self.assertEqual(row["comment"], "")

	def test_the_rows_are_still_the_rows_of_the_order(self):
		invoice = place_order(CAPTAIN, [(FOOD_ITEM, 1), (FOOD_ITEM, 2, "わさび抜き")], table=TABLES[0])
		self.assertEqual(len(self._items(invoice)), len(frappe.get_doc("POS Invoice", invoice).items))
