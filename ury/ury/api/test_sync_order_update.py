"""Changing an order that already exists (`sync_order` with an invoice).

A user who is not a "billing user" of the POS Profile (not in `role_allowed_for_billing`: a
captain, and a manager on the default setup) takes orders and adds dishes to them. Editing from
the order list sends no `last_modified_time`; that must not be taken for a second order on an
occupied table (the old behaviour: "This order has been modified" for every captain). Run on the
test site only.
"""

import frappe
from frappe.utils import add_to_date

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
	print_bill,
)


class TestUpdateAnOrder(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		open_pos(CASHIER)
		billing_roles = {row.role for row in frappe.get_doc("POS Profile", POS_PROFILE).role_allowed_for_billing}
		# the point of these tests: neither of them is a billing user
		for user in (CAPTAIN, MANAGER):
			self.assertFalse(billing_roles & set(frappe.get_roles(user)), user)

	def _items(self, invoice):
		return frappe.get_all("POS Invoice Item", filters={"parent": invoice}, pluck="item_code", order_by="idx")

	def _kots(self, invoice):
		return frappe.get_all(
			"URY KOT", filters={"invoice": invoice}, fields=["name", "type"], order_by="creation"
		)

	def _kot_items(self, kot):
		return frappe.get_all("URY KOT Items", filters={"parent": kot}, pluck="item", order_by="idx")

	def _add_a_dish(self, user):
		name = place_order(user, [(FOOD_ITEM, 1)], order_type="Take Away")
		invoices, kots_before = frappe.db.count("POS Invoice"), {kot.name for kot in self._kots(name)}
		# the order list sends the invoice but no modified time
		again = place_order(user, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)], order_type="Take Away", invoice=name)
		self.assertEqual(again, name)
		self.assertEqual(frappe.db.count("POS Invoice"), invoices, "no second order")
		self.assertEqual(self._items(name), [FOOD_ITEM, ALCOHOL_ITEM])
		new_kots = [kot for kot in self._kots(name) if kot.name not in kots_before]
		self.assertTrue(new_kots)
		sent = [item for kot in new_kots for item in self._kot_items(kot.name)]
		self.assertEqual(sent, [ALCOHOL_ITEM], "the kitchen gets the new dish only, not the whole order again")

	def test_a_captain_adds_a_dish_without_a_modified_time(self):
		self._add_a_dish(CAPTAIN)

	def test_a_manager_adds_a_dish_without_a_modified_time(self):
		self._add_a_dish(MANAGER)

	def test_the_cashier_still_can(self):
		self._add_a_dish(CASHIER)

	def test_the_matching_modified_time_is_accepted(self):
		name = place_order(CAPTAIN, [(FOOD_ITEM, 1)], order_type="Take Away")
		modified = frappe.db.get_value("POS Invoice", name, "modified")
		place_order(CAPTAIN, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)], order_type="Take Away", invoice=name, last_modified_time=modified)
		self.assertEqual(self._items(name), [FOOD_ITEM, ALCOHOL_ITEM])

	def test_an_old_modified_time_is_still_refused(self):
		name = place_order(CAPTAIN, [(FOOD_ITEM, 1)], order_type="Take Away")
		modified = frappe.db.get_value("POS Invoice", name, "modified")
		with self.assertRaises(frappe.ValidationError):
			place_order(
				CAPTAIN,
				[(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)],
				order_type="Take Away",
				invoice=name,
				last_modified_time=add_to_date(modified, seconds=-5),
			)
		self.assertEqual(self._items(name), [FOOD_ITEM])

	def test_a_captain_cannot_change_a_printed_order(self):
		name = place_order(CAPTAIN, [(FOOD_ITEM, 1)], order_type="Take Away")
		print_bill(name, CAPTAIN)
		with self.assertRaises(frappe.ValidationError):
			place_order(CAPTAIN, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)], order_type="Take Away", invoice=name)
		self.assertEqual(self._items(name), [FOOD_ITEM])

	def test_a_captain_may_add_to_the_order_of_another_user(self):
		"""An order has no owner to protect (2026-11); see test_captain_access for the limits that remain."""
		name = place_order(CASHIER, [(FOOD_ITEM, 1)], order_type="Take Away")
		place_order(CAPTAIN, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)], order_type="Take Away", invoice=name)
		self.assertEqual(self._items(name), [FOOD_ITEM, ALCOHOL_ITEM])

	def test_a_new_order_on_a_table_with_an_unprinted_order_is_still_refused(self):
		place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])
		count = frappe.db.count("POS Invoice")
		with self.assertRaises((frappe.ValidationError, frappe.PermissionError)):
			place_order(CAPTAIN, [(ALCOHOL_ITEM, 1)], table=TABLES[0])
		self.assertEqual(frappe.db.count("POS Invoice"), count)
