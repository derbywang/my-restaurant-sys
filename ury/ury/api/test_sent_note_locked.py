"""The note of a dish that already went to the kitchen cannot be changed (`sync_order`, 3.5.1).

Changing a note does not change the quantity, and the kitchen is told only about quantities, so the screen
would show a note the kitchen never got. To change it, take the dish back and add it again with the new note
(only someone who may take dishes back can); a dish added now may carry its own note. Run on the test site only.
"""

import frappe

from ury.setup.test_site import (
	ALCOHOL_ITEM,
	CAPTAIN,
	CASHIER,
	FOOD_ITEM,
	MANAGER,
	POS_PROFILE,
	TABLES,
	URYFlowTestCase,
	open_pos,
	place_order,
)

TABLE = TABLES[0]


def notes_of(name, item=ALCOHOL_ITEM):
	return [
		(row.qty, row.comment or "")
		for row in frappe.get_all(
			"POS Invoice Item", filters={"parent": name, "item_code": item}, fields=["qty", "comment"], order_by="idx"
		)
	]


def tickets_since(name, before):
	"""(sent, taken_back) as {(item, note): quantity} of the kitchen tickets made after `before`."""
	sent, taken_back = {}, {}
	for ticket in frappe.get_all("URY KOT", filters={"invoice": name}, fields=["name", "type"]):
		if ticket.name in before:
			continue
		for row in frappe.get_all(
			"URY KOT Items", filters={"parent": ticket.name}, fields=["item", "quantity", "cancelled_qty", "comments"]
		):
			key = (row.item, row.comments or "")
			if ticket.type in ("New Order", "Order Modified"):
				sent[key] = sent.get(key, 0) + int(row.quantity)
			else:
				taken_back[key] = taken_back.get(key, 0) + int(row.cancelled_qty or 0)
	return sent, taken_back


class TestSentNoteLocked(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		open_pos(CASHIER)
		original = frappe.db.get_value("POS Profile", POS_PROFILE, "remove_items")
		self.addCleanup(self._remove_items, original)
		self._remove_items(1)  # taking dishes back is allowed for those who may (the cashier, the manager)

	def _remove_items(self, value):
		frappe.db.set_value("POS Profile", POS_PROFILE, "remove_items", value)
		frappe.db.commit()
		frappe.clear_document_cache("POS Profile", POS_PROFILE)

	def _sent(self, user=CAPTAIN, note="冷えたもの", quantity=2, table=TABLE):
		name = place_order(user, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, quantity, note)], table=table)
		frappe.db.commit()  # as the request does; a refused change below is rolled back on its own
		return name

	def _refused(self, user, name, items):
		table = frappe.db.get_value("POS Invoice", name, "restaurant_table")
		with self.assertRaises(frappe.ValidationError) as caught:
			place_order(user, items, table=table, invoice=name)
		self.assertNotIsInstance(caught.exception, frappe.PermissionError)
		self.assertIn("Sent note locked", [m.get("title") for m in frappe.local.message_log])
		frappe.db.rollback()

	def test_the_note_of_a_sent_dish_cannot_be_changed(self):
		name = self._sent()
		self._refused(CAPTAIN, name, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 2, "ぬるめ")])
		self.assertEqual(notes_of(name), [(2, "冷えたもの")])

	def test_nor_can_it_be_taken_away_or_written_where_there_was_none(self):
		name = self._sent()
		self._refused(CAPTAIN, name, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 2, "")])
		self.assertEqual(notes_of(name), [(2, "冷えたもの")])
		plain = self._sent(note="", quantity=1, table=TABLES[1])
		self._refused(CAPTAIN, plain, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1, "冷えたもの")])
		self.assertEqual(notes_of(plain), [(1, "")])

	def test_the_lock_does_not_ask_who_it_is(self):
		for user, table in ((CASHIER, TABLES[0]), (MANAGER, TABLES[1])):
			name = self._sent(user=user, table=table)
			self._refused(user, name, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 2, "ぬるめ")])
			self.assertEqual(notes_of(name), [(2, "冷えたもの")])

	def test_the_same_note_goes_through_and_a_space_does_not_count(self):
		name = self._sent()
		place_order(CAPTAIN, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 2, " 冷えたもの ")], table=TABLE, invoice=name)
		place_order(CAPTAIN, [(FOOD_ITEM, 2), (ALCOHOL_ITEM, 2, "冷えたもの")], table=TABLE, invoice=name)
		self.assertEqual(frappe.db.get_value("POS Invoice Item", {"parent": name, "item_code": FOOD_ITEM}, "qty"), 2)

	def test_one_more_of_the_same_dish_may_have_its_own_note_and_the_kitchen_gets_only_that(self):
		name = self._sent()
		before = set(frappe.get_all("URY KOT", filters={"invoice": name}, pluck="name"))
		place_order(
			CAPTAIN, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 2, "冷えたもの"), (ALCOHOL_ITEM, 1, "ぬるめ")], table=TABLE, invoice=name
		)
		self.assertEqual(notes_of(name), [(2, "冷えたもの"), (1, "ぬるめ")])
		sent, taken_back = tickets_since(name, before)
		self.assertEqual(sent, {(ALCOHOL_ITEM, "ぬるめ"): 1})
		self.assertEqual(taken_back, {})

	def test_the_cashier_takes_the_dish_back_and_adds_it_with_the_new_note(self):
		name = self._sent(user=CAPTAIN)
		before = set(frappe.get_all("URY KOT", filters={"invoice": name}, pluck="name"))
		place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLE, invoice=name)  # taken back
		place_order(CASHIER, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 2, "ぬるめ")], table=TABLE, invoice=name)  # added again
		self.assertEqual(notes_of(name), [(2, "ぬるめ")])
		sent, taken_back = tickets_since(name, before)
		self.assertEqual(taken_back.get((ALCOHOL_ITEM, "")) or taken_back.get((ALCOHOL_ITEM, "冷えたもの")), 2)
		self.assertEqual(sent, {(ALCOHOL_ITEM, "ぬるめ"): 2})

	def test_the_captain_cannot_take_the_dish_back_so_cannot_do_the_same(self):
		name = self._sent(user=CAPTAIN)
		with self.assertRaises(frappe.PermissionError):
			place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLE, invoice=name)
		frappe.db.rollback()
		self.assertEqual(notes_of(name), [(2, "冷えたもの")])

	def test_less_of_a_dish_and_a_new_note_in_one_go_is_a_changed_note(self):
		name = self._sent(user=CASHIER)
		self._refused(CASHIER, name, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1, "ぬるめ")])
		self.assertEqual(notes_of(name), [(2, "冷えたもの")])

	def test_a_dish_that_is_not_sent_yet_has_no_lock(self):
		name = self._sent()
		place_order(CAPTAIN, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 2, "冷えたもの")], table=TABLE, invoice=name)
		# a dish that was never on the order: any note
		place_order(
			CAPTAIN, [(FOOD_ITEM, 1, "わさび抜き"), (FOOD_ITEM, 1), (ALCOHOL_ITEM, 2, "冷えたもの")], table=TABLE, invoice=name
		)
		self.assertEqual(sorted(notes_of(name, FOOD_ITEM)), [(1, ""), (1, "わさび抜き")])
