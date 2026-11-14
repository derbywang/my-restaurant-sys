"""A waiter works on the shift the cashier opened (2026-11-14).

The waiter has no shift of her own and may not open one. The POS asks `get_shift_state` whether the shop's register is
open: the same question ERPNext asks when an order is saved (an open, submitted POS Opening Entry of the POS Profile,
whoever opened it). The opening screen of the cashier lists the payment modes with their type, so that the cash mode
is shown as 「現金」 whatever it is called on the site. Run on the test site only.
"""

import frappe

from ury.ury.api import pos_permissions
from ury.ury_pos.api import get_pos_opening_screen_data as OPENING_SCREEN
from ury.setup.test_site import CAPTAIN, CASHIER, POS_PROFILE, URYFlowTestCase, as_user, open_pos


class TestShiftState(URYFlowTestCase):
	def state_for(self, user):
		with as_user(user):
			return pos_permissions.get_shift_state()

	def test_no_shift_is_open_before_the_cashier_opens_one(self):
		state = self.state_for(CAPTAIN)
		self.assertFalse(state["open"])
		self.assertIsNone(state["opened_by"])

	def test_the_waiter_sees_the_shift_the_cashier_opened(self):
		open_pos(CASHIER)
		state = self.state_for(CAPTAIN)
		self.assertTrue(state["open"])
		self.assertEqual(state["opened_by"], CASHIER)

	def test_the_waiter_has_no_shift_of_her_own_and_may_not_open_one(self):
		open_pos(CASHIER)
		with as_user(CAPTAIN):
			self.assertFalse(frappe.has_permission("POS Opening Entry", "create"))
			self.assertFalse(pos_permissions.get_pos_permissions()["open_shift"])
		self.assertFalse(frappe.db.exists("POS Opening Entry", {"user": CAPTAIN}))

	def test_a_shift_that_is_closed_does_not_count(self):
		opening = open_pos(CASHIER)
		frappe.db.set_value("POS Opening Entry", opening.name, "status", "Closed")
		self.assertFalse(self.state_for(CAPTAIN)["open"])

	def test_a_shift_that_is_not_submitted_does_not_count(self):
		opening = open_pos(CASHIER)
		frappe.db.set_value("POS Opening Entry", opening.name, "docstatus", 0)
		self.assertFalse(self.state_for(CAPTAIN)["open"])

	def test_a_shift_of_another_pos_profile_does_not_count(self):
		opening = open_pos(CASHIER)
		frappe.db.set_value("POS Opening Entry", opening.name, "pos_profile", "no-such-profile")
		self.assertFalse(self.state_for(CAPTAIN)["open"])
		self.assertTrue(POS_PROFILE)

	def test_the_question_changes_nothing(self):
		open_pos(CASHIER)
		before = frappe.db.count("POS Opening Entry")
		self.state_for(CAPTAIN)
		self.assertEqual(frappe.db.count("POS Opening Entry"), before)

	def test_the_waiter_can_take_an_order_on_the_cashiers_shift(self):
		from ury.setup.test_site import FOOD_ITEM, TABLES, place_order

		open_pos(CASHIER)
		invoice = place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLES[0])
		self.assertTrue(frappe.db.exists("POS Invoice", invoice))


class TestOpeningScreenModes(URYFlowTestCase):
	def test_the_payment_modes_of_the_opening_screen_have_their_type(self):
		with as_user(CASHIER):
			data = OPENING_SCREEN()
		modes = {row["mode_of_payment"]: row for row in data["payment_modes"]}
		self.assertIn("Cash", modes)
		self.assertEqual(modes["Cash"].get("type"), "Cash")
		for row in modes.values():
			self.assertEqual(row.get("type"), frappe.db.get_value("Mode of Payment", row["mode_of_payment"], "type"))
