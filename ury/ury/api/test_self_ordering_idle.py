"""A guest page that does nothing but wait must still learn that the ordering is over (found in the browser, 2026-11-20).

The page asks `get_customer_order` every 30 seconds; that call may be read after the table was closed (so a guest can still see
the order, test_a_guest_can_still_read_the_order_after_the_table_was_closed) and so it refused nothing: the page showed the menu
until the guest pressed a dish. The answer now says whether the ordering is open (`ordering`: "open", "table_closed" or
"store_closed", the same rules as `_resolve_session`), so that the page can show its notice by itself. Run on the test site only."""

import frappe

from ury.setup.test_site import CASHIER, as_user, close_shift, pay_order, print_bill
from ury.ury.api.self_ordering import get_customer_order
from ury.ury.api.test_self_ordering_table import PROFILE, TABLE, SelfOrderingCase


class TestTheIdlePageLearnsThatOrderingIsOver(SelfOrderingCase):
	def test_an_open_table_says_open(self):
		self.staff_open()
		session = self.scan()
		self.assertEqual(get_customer_order(session)["ordering"], "open")
		self.order(session)
		self.assertEqual(get_customer_order(session)["ordering"], "open")

	def test_a_closed_table_says_so_with_or_without_an_order(self):
		self.staff_open()
		without = self.scan()
		self.staff_close()
		self.assertEqual(get_customer_order(without)["ordering"], "table_closed")

		self.staff_open()
		with_order = self.scan()
		self.order(with_order)
		self.staff_close()
		answer = get_customer_order(with_order)
		self.assertEqual(answer["ordering"], "table_closed")
		self.assertEqual(len(answer["items"]), 1)  # the order can still be read

	def test_a_table_opened_again_is_closed_for_the_guests_before(self):
		self.staff_open()
		old = self.scan()
		self.staff_close()
		self.staff_open()
		self.assertEqual(get_customer_order(old)["ordering"], "table_closed")

	def test_an_order_that_was_paid_says_it_too(self):
		self.staff_open()
		session = self.scan()
		invoice = self.order(session)["invoice"]
		pay_order(invoice)
		answer = get_customer_order(session)
		self.assertEqual(answer["state"], "paid")
		self.assertEqual(answer["ordering"], "table_closed")

	def test_a_closed_shift_says_store_closed(self):
		self.staff_open()
		session = self.scan()
		close_shift(self.opening)
		self.assertEqual(get_customer_order(session)["ordering"], "store_closed")


class TestWhatTheNoticeDoesToABillThatWasAskedForOrPrinted(SelfOrderingCase):
	"""The guest pressed お会計, or the staff printed the bill, or the order was paid: the page showed the order and no buttons.
	While the table is OPEN (the bill is only asked for) nothing changes: the page goes on showing it. When the table was closed
	(printing the bill, paying and cancelling close it) the notice covers the page as it does for any closed table, and the
	answer still says billed / bill_requested (the order can be read, the page chooses to cover it)."""

	def _bill_request_on(self):
		original = frappe.db.get_value("URY Self Ordering Profile", PROFILE, "enable_request_bill")
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, "enable_request_bill", 1)
		frappe.db.commit()
		self.addCleanup(
			lambda: (frappe.db.set_value("URY Self Ordering Profile", PROFILE, "enable_request_bill", original), frappe.db.commit())
		)

	def test_asking_for_the_bill_does_not_close_the_ordering(self):
		from ury.ury.api.self_ordering import request_bill

		self._bill_request_on()
		self.staff_open()
		session = self.scan()
		self.order(session)
		request_bill(session)
		answer = get_customer_order(session)
		self.assertTrue(answer["bill_requested"])
		self.assertEqual(answer["ordering"], "open")

	def test_when_the_staff_print_the_bill_the_ordering_is_over_and_the_order_still_says_billed(self):
		from ury.ury.api.self_ordering import request_bill

		self._bill_request_on()
		self.staff_open()
		session = self.scan()
		invoice = self.order(session)["invoice"]
		request_bill(session)
		print_bill(invoice, CASHIER)
		answer = get_customer_order(session)
		self.assertTrue(answer["billed"])
		self.assertEqual(answer["ordering"], "table_closed")

	def test_a_split_bill_with_a_part_still_open_keeps_the_ordering_open(self):
		"""The page that moves to the other part of a split bill (bill-switch) must not be covered while the table is open."""
		from ury.ury.doctype.ury_order.ury_order import split_bill

		self.staff_open()
		session = self.scan()
		invoice = self.order(session, quantity=2)["invoice"]  # a part is taken off, at least one stays on the bill
		doc = frappe.get_doc("POS Invoice", invoice)
		with as_user(CASHIER):
			split_bill(invoice, [{"name": doc.items[0].name, "qty": 1}])
		frappe.db.commit()
		answer = get_customer_order(session)
		self.assertEqual(answer["ordering"], "open")
