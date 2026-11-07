"""A cancel ticket takes back what the kitchen got, no more (`process_items_for_cancel_kot`).

The cancel tickets used to be made from the lines of the order, whether or not the kitchen ever got them, and sent
to the production units by the menu as it is when the order is cancelled. Now they are made from the tickets the
kitchen was sent (per production unit, dish and note; all the orders of a split bill together), and go to the units
that got the dish. Run on the test site only.
"""

import frappe

from ury.setup.test_site import (
	ALCOHOL_ITEM,
	CASHIER,
	FOOD_ITEM,
	POS_PROFILE,
	PRODUCTION_UNIT,
	TABLES,
	URYFlowTestCase,
	as_user,
	open_pos,
	place_order,
	print_bill,
)
from ury.ury.api.test_no_kitchen import NoKitchenForBeer
from ury.ury.doctype.ury_order.ury_order import cancel_order, split_bill
from ury.ury_pos.api import merge_bills

BEER = ALCOHOL_ITEM
CANCELLING = ("Cancelled", "Partially cancelled")
SENDING = ("New Order", "Order Modified")
GONE = "Unit that is gone"


def tickets(invoices, types):
	return frappe.get_all(
		"URY KOT",
		filters={"invoice": ["in", list(invoices)], "type": ["in", list(types)], "docstatus": ["in", [1, 2]]},
		fields=["name", "invoice", "type", "production", "original_kot"],
		order_by="creation",
	)


def rows(invoices, types, field):
	"""[(production, item, comments, quantity of `field`)] of the tickets of these types."""
	found = []
	for ticket in tickets(invoices, types):
		for row in frappe.get_all(
			"URY KOT Items", filters={"parent": ticket.name}, fields=["item", "comments", field], order_by="idx"
		):
			found.append((ticket.production, row.item, row.comments or "", int(row.get(field) or 0)))
	return found


def total(found, item):
	return sum(row[3] for row in found if row[1] == item)


class LedgerCase(NoKitchenForBeer, URYFlowTestCase):
	def setUp(self):
		super().setUp()
		open_pos(CASHIER)
		original = frappe.db.get_value("POS Profile", POS_PROFILE, "remove_items")
		self.addCleanup(self._remove_items, original)
		self._remove_items(1)  # taking dishes back is allowed for those who may

	def _remove_items(self, value):
		frappe.db.set_value("POS Profile", POS_PROFILE, "remove_items", value)
		frappe.db.commit()
		frappe.clear_document_cache("POS Profile", POS_PROFILE)

	def order(self, items, table=TABLES[0], invoice=None, user=CASHIER):
		name = place_order(user, items, table=table, invoice=invoice)
		frappe.db.commit()
		return name

	def cancel(self, invoice):
		with as_user(CASHIER):
			cancel_order(invoice, "test")

	def beer_back(self):
		"""The beer is in the kitchen's menu again (as when someone fixes the configuration afterwards)."""
		self._put_beer_back()

	def sent(self, *invoices):
		return rows(invoices, SENDING, "quantity")

	def cancelled(self, *invoices):
		return rows(invoices, CANCELLING, "cancelled_qty")


class TestCancelWhatTheKitchenGot(LedgerCase):
	def test_a_dish_the_kitchen_never_got_is_not_in_the_cancel_ticket(self):
		self.leave_beer_without_kitchen()
		name = self.order([(FOOD_ITEM, 1), (BEER, 2)])
		self.assertEqual(total(self.sent(name), BEER), 0)
		self.beer_back()
		self.cancel(name)
		cancelled = self.cancelled(name)
		self.assertEqual(total(cancelled, FOOD_ITEM), 1)
		self.assertEqual(total(cancelled, BEER), 0)

	def test_an_order_the_kitchen_never_got_makes_no_cancel_ticket(self):
		self.leave_beer_without_kitchen()
		name = self.order([(BEER, 2)])
		self.assertFalse(tickets([name], SENDING))
		self.beer_back()
		self.cancel(name)
		self.assertFalse(tickets([name], CANCELLING))

	def test_what_was_added_without_a_kitchen_is_not_cancelled(self):
		name = self.order([(FOOD_ITEM, 1), (BEER, 1)])
		self.leave_beer_without_kitchen()
		self.order([(FOOD_ITEM, 1), (BEER, 3)], invoice=name)  # two more beers: no ticket
		self.assertEqual(total(self.sent(name), BEER), 1)
		self.beer_back()
		self.cancel(name)
		self.assertEqual(total(self.cancelled(name), BEER), 1)

	def test_two_lines_with_other_notes_only_one_of_them_sent(self):
		name = self.order([(FOOD_ITEM, 1), (BEER, 1, "冷えたもの")])
		self.leave_beer_without_kitchen()
		self.order([(FOOD_ITEM, 1), (BEER, 1, "冷えたもの"), (BEER, 1, "ぬるめ")], invoice=name)
		self.beer_back()
		self.cancel(name)
		beers = [row for row in self.cancelled(name) if row[1] == BEER]
		self.assertEqual([(row[2], row[3]) for row in beers], [("冷えたもの", 1)])

	def test_the_ticket_goes_to_the_unit_that_got_the_dish(self):
		name = self.order([(FOOD_ITEM, 1), (BEER, 2)])
		self.leave_beer_without_kitchen()  # the beer is moved away from the unit afterwards
		self.cancel(name)
		cancelled = self.cancelled(name)
		self.assertIn((PRODUCTION_UNIT, BEER, "", 2), cancelled)
		self.assertEqual({row[0] for row in cancelled}, {PRODUCTION_UNIT})

	def test_the_cancel_ticket_names_the_tickets_it_takes_back(self):
		name = self.order([(FOOD_ITEM, 1), (BEER, 2)])
		originals = {t.name for t in tickets([name], SENDING)}
		self.cancel(name)
		listed = {n for t in tickets([name], CANCELLING) for n in (t.original_kot or "").split(",") if n}
		self.assertTrue(listed)
		self.assertLessEqual(listed, originals)


class TestTakingADishBack(LedgerCase):
	def test_taking_back_a_dish_the_kitchen_never_got_makes_no_ticket(self):
		self.leave_beer_without_kitchen()
		name = self.order([(FOOD_ITEM, 1), (BEER, 2)])
		self.beer_back()
		self.order([(FOOD_ITEM, 1), (BEER, 1)], invoice=name)
		self.assertEqual(total(self.cancelled(name), BEER), 0)

	def test_taking_back_more_than_the_kitchen_got_cancels_only_what_it_got(self):
		name = self.order([(FOOD_ITEM, 1), (BEER, 2)])
		self.leave_beer_without_kitchen()
		self.order([(FOOD_ITEM, 1), (BEER, 5)], invoice=name)  # three more, no ticket
		self.beer_back()
		self.order([(FOOD_ITEM, 1)], invoice=name)  # the beer is taken off the order
		self.assertEqual(total(self.sent(name), BEER), 2)
		self.assertEqual(total(self.cancelled(name), BEER), 2)

	def test_taking_back_and_then_cancelling_cancels_each_dish_once(self):
		name = self.order([(FOOD_ITEM, 1), (BEER, 3)])
		self.order([(FOOD_ITEM, 1), (BEER, 1)], invoice=name)
		self.assertEqual(total(self.cancelled(name), BEER), 2)
		self.cancel(name)
		self.assertEqual(total(self.cancelled(name), BEER), 3)


class TestTheUnitIsGone(LedgerCase):
	def test_the_order_is_cancelled_and_the_trouble_is_logged(self):
		name = self.order([(FOOD_ITEM, 1)])
		ticket = tickets([name], SENDING)[0].name
		frappe.db.set_value("URY KOT", ticket, "production", GONE)  # the database does not check the link
		frappe.db.commit()
		self.addCleanup(self._restore, ticket)
		self.cancel(name)
		self.assertEqual(frappe.db.get_value("POS Invoice", name, "docstatus"), 2)
		self.assertFalse(tickets([name], CANCELLING))
		logged = frappe.get_all(
			"Error Log", filters={"method": "KOT Error", "error": ["like", f"%{name}%"]}, pluck="name"
		)
		self.assertTrue(logged)

	def _restore(self, ticket):
		frappe.db.set_value("URY KOT", ticket, "production", PRODUCTION_UNIT)
		frappe.db.commit()


class TestSplitBill(LedgerCase):
	def _split_beer(self, quantity, in_bill=2):
		source = self.order([(FOOD_ITEM, 1), (BEER, in_bill)])
		print_bill(source)
		row = frappe.db.get_value("POS Invoice Item", {"parent": source, "item_code": BEER}, "name")
		with as_user(CASHIER):
			new = split_bill(source, [{"name": row, "qty": quantity}])["new_invoice"]
		frappe.db.commit()
		return source, new

	def test_the_new_bill_cancels_the_dishes_the_kitchen_got_for_the_old_one(self):
		source, new = self._split_beer(2)
		self.assertFalse(tickets([new], SENDING))
		self.cancel(new)
		cancelled = self.cancelled(new)
		self.assertIn((PRODUCTION_UNIT, BEER, "", 2), cancelled)
		listed = {n for t in tickets([new], CANCELLING) for n in (t.original_kot or "").split(",") if n}
		self.assertTrue(listed & {t.name for t in tickets([source], SENDING)})

	def test_taking_a_dish_back_from_the_new_bill_is_limited_to_what_the_kitchen_got(self):
		source, new = self._split_beer(2)
		self.order([(BEER, 1)], invoice=new)
		self.assertEqual(total(self.cancelled(new), BEER), 1)
		self.cancel(new)
		self.assertEqual(total(self.cancelled(new), BEER), 2)

	def test_both_bills_together_never_cancel_more_than_the_kitchen_got(self):
		source, new = self._split_beer(1)
		self.cancel(new)
		self.cancel(source)
		self.assertEqual(total(self.sent(source, new), BEER), 2)
		self.assertEqual(total(self.cancelled(source, new), BEER), 2)
		self.assertEqual(total(self.cancelled(new), BEER), 1)
		self.assertEqual(total(self.cancelled(source), BEER), 1)


class TestMergedBill(LedgerCase):
	def test_each_bill_cancels_its_own_dishes_once(self):
		first = self.order([(FOOD_ITEM, 1), (BEER, 1)], table=TABLES[0])
		second = self.order([(FOOD_ITEM, 1), (BEER, 2)], table=TABLES[1])
		print_bill(first)
		print_bill(second)
		with as_user(CASHIER):
			merge_bills(first, second)
		frappe.db.commit()
		self.cancel(first)
		self.assertEqual(total(self.cancelled(first), BEER), 1)
		self.assertEqual(total(self.cancelled(second), BEER), 0)
		self.cancel(second)
		self.assertEqual(total(self.cancelled(second), BEER), 2)
		self.assertEqual(total(self.cancelled(first, second), BEER), total(self.sent(first, second), BEER))


class TestAnAmendedTicket(LedgerCase):
	def test_a_cancelled_and_amended_ticket_is_counted_once(self):
		name = self.order([(FOOD_ITEM, 1), (BEER, 2)])
		ticket = [t.name for t in tickets([name], SENDING)][0]
		with as_user("Administrator"):
			original = frappe.get_doc("URY KOT", ticket)
			original.cancel()  # in the Desk: cancel the ticket and amend it
			amended = frappe.copy_doc(original)
			amended.docstatus = 0
			amended.amended_from = original.name
			amended.insert()
			amended.submit()
		frappe.db.commit()
		self.assertEqual(frappe.db.get_value("URY KOT", ticket, "docstatus"), 2)
		self.leave_beer_without_kitchen()
		self.order([(FOOD_ITEM, 1), (BEER, 4)], invoice=name)  # two more beers, no ticket
		self.beer_back()
		self.cancel(name)
		self.assertEqual(total(self.cancelled(name), BEER), 2)
