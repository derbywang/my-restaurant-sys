"""An order that is with the kitchen cannot be changed to no dish at all by `sync_order` (2026-11-14): the register showed
「注文はまだありません」 after the last line was deleted and offered no way to save, while the order was unchanged and the kitchen had
been told nothing. Taking the whole order back is the cancel of the order (one cancel ticket for everything). Run on the test site only."""

import frappe

from ury.setup.test_site import CASHIER, FOOD_ITEM, POS_PROFILE, URYFlowTestCase, as_user, open_pos, place_order
from ury.ury.doctype.ury_order.ury_order import sync_order


class TestSyncOrderToNothing(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		open_pos(CASHIER)
		original = frappe.db.get_value("POS Profile", POS_PROFILE, "remove_items")
		self.addCleanup(self._set_remove_items, original)
		self._set_remove_items(1)  # the cashier may take dishes back

	def _set_remove_items(self, value):
		frappe.db.set_value("POS Profile", POS_PROFILE, "remove_items", value)
		frappe.db.commit()
		frappe.clear_document_cache("POS Profile", POS_PROFILE)

	def _send_nothing(self, invoice):
		profile = frappe.get_doc("POS Profile", POS_PROFILE)
		with as_user(CASHIER):
			return sync_order(
				items=[], cashier=CASHIER, owner=CASHIER, mode_of_payment=profile.payments[0].mode_of_payment,
				customer=frappe.db.get_value("POS Invoice", invoice, "customer"), no_of_pax=1, last_invoice=None,
				waiter=CASHIER, pos_profile=POS_PROFILE, table=None, invoice=invoice, order_type="Take Away",
			)

	def test_an_order_that_is_with_the_kitchen_is_not_emptied_and_the_message_says_how_to_cancel_it(self):
		invoice = place_order(CASHIER, [(FOOD_ITEM, 2)], order_type="Take Away")
		tickets = frappe.db.count("URY KOT", {"invoice": invoice})
		with self.assertRaises(frappe.ValidationError) as caught:
			self._send_nothing(invoice)
		self.assertIn("cancel", str(caught.exception).lower())
		# nothing changed: the order, the tickets
		self.assertEqual([(row.item_code, row.qty) for row in frappe.get_doc("POS Invoice", invoice).items], [(FOOD_ITEM, 2)])
		self.assertEqual(frappe.db.count("URY KOT", {"invoice": invoice}), tickets)
