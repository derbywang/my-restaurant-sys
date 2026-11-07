"""Who may cancel an order or take dishes back, and what the kitchen gets then (cashier and manager alike).

The tickets of the kitchen are made by the system on behalf of the one who cancels (`cancel_order`) or changes the
order (`sync_order`): that person needs the right on the order, not on the tickets. Run on the test site only.
"""

import frappe

from ury.setup.test_site import CAPTAIN, CASHIER, FOOD_ITEM, MANAGER, TABLES, as_user, place_order
from ury.ury.api.test_cancel_kot_ledger import BEER, CANCELLING, SENDING, LedgerCase, tickets, total
from ury.ury.doctype.ury_order.ury_order import cancel_order


class RolesCase(LedgerCase):
	USER = CASHIER

	def trouble(self, invoice):
		return frappe.get_all(
			"Error Log", filters={"method": "KOT Error", "error": ["like", f"%{invoice}%"]}, pluck="name"
		)

	def cancel_as(self, invoice):
		with as_user(self.USER):
			cancel_order(invoice, "test")

	def test_cancelling_makes_the_cancel_ticket(self):
		name = self.order([(FOOD_ITEM, 1), (BEER, 2)])
		self.cancel_as(name)
		self.assertEqual(frappe.db.get_value("POS Invoice", name, "docstatus"), 2)
		self.assertEqual(total(self.cancelled(name), BEER), 2)
		self.assertEqual(total(self.cancelled(name), FOOD_ITEM), 1)

	def test_cancelling_voids_the_tickets_that_were_sent(self):
		name = self.order([(FOOD_ITEM, 1), (BEER, 2)])
		sent = [t.name for t in tickets([name], SENDING)]
		self.assertTrue(sent)
		self.cancel_as(name)
		self.assertEqual({frappe.db.get_value("URY KOT", n, "docstatus") for n in sent}, {2})

	def test_cancelling_leaves_nothing_in_the_error_log(self):
		name = self.order([(FOOD_ITEM, 1), (BEER, 2)])
		self.cancel_as(name)
		self.assertEqual(self.trouble(name), [])

	def test_taking_a_dish_back_makes_the_cancel_ticket(self):
		name = self.order([(FOOD_ITEM, 1), (BEER, 3)])
		place_order(self.USER, [(FOOD_ITEM, 1), (BEER, 1)], table=TABLES[0], invoice=name)
		self.assertEqual(total(self.cancelled(name), BEER), 2)
		self.assertEqual({t.type for t in tickets([name], CANCELLING)}, {"Partially cancelled"})


class TestTheCashier(RolesCase):
	USER = CASHIER


class TestTheManager(RolesCase):
	USER = MANAGER


class TestTheCaptain(LedgerCase):
	"""The waiter only takes orders: cancelling a whole order is for the cashier and the manager."""

	def test_cancelling_an_order_is_refused_and_nothing_changes(self):
		name = self.order([(FOOD_ITEM, 1), (BEER, 2)], user=CAPTAIN)
		sent = {t.name: t.docstatus for t in frappe.get_all("URY KOT", filters={"invoice": name}, fields=["name", "docstatus"])}
		self.assertTrue(sent)
		with as_user(CAPTAIN):
			with self.assertRaises(frappe.PermissionError):
				cancel_order(name, "test")
		frappe.db.rollback()
		self.assertEqual(frappe.db.get_value("POS Invoice", name, "docstatus"), 0)
		self.assertEqual(
			{t.name: t.docstatus for t in frappe.get_all("URY KOT", filters={"invoice": name}, fields=["name", "docstatus"])}, sent
		)
		self.assertFalse(tickets([name], CANCELLING))
		self.assertEqual(frappe.db.get_value("URY Table", TABLES[0], "occupied"), 1)

	def test_the_captain_has_no_cancel_right_on_orders(self):
		self.assertFalse(frappe.has_permission("POS Invoice", "cancel", user=CAPTAIN))


class TestTheRightsOnTheTickets(LedgerCase):
	"""Nobody but the administrators cancels or deletes a kitchen ticket in the Desk: that goes round the ledger and the
	cancel tickets (a deleted ticket leaves no trace). Cancelling an order voids the tickets as a system step, and the
	tickets are made with the create and submit rights, which stay."""

	def roles(self, right):
		return set(frappe.permissions.get_doctype_roles("URY KOT", right))

	def test_the_waiter_the_cashier_and_the_manager_cannot_cancel_a_ticket(self):
		self.assertFalse(self.roles("cancel") & {"URY Captain", "URY Cashier", "URY Manager"})
		self.assertIn("URY Admin", self.roles("cancel"))

	def test_nor_delete_one(self):
		self.assertFalse(self.roles("delete") & {"URY Captain", "URY Cashier", "URY Manager"})
		self.assertIn("URY Admin", self.roles("delete"))

	def test_they_still_make_and_submit_tickets(self):
		for right in ("create", "submit"):
			self.assertTrue(self.roles(right) >= {"URY Captain", "URY Cashier", "URY Manager"}, right)
