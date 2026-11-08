"""A table that has a split bill is not freed while another part of the bill is not printed.

One table, two bills (会計分割): printing, cancelling or moving one of them used to free the whole table at once, and
the next guests could be seated at a table where the other part of the bill was not paid. Now the table is freed
(and self ordering on it closed) only when no other part of the same split group that is on the table is still
unprinted. A bill that was not split behaves as before. The session of a phone or a tablet whose order can take no
more dishes follows to the part that is still open. Run on the test site only.
"""

import frappe

from ury.setup.test_site import (
	ALCOHOL_ITEM,
	CAPTAIN,
	CASHIER,
	FOOD_ITEM,
	MANAGER,
	TABLES,
	as_user,
	pay_order,
	place_order,
	print_bill,
)
from ury.ury.api import self_ordering as so
from ury.ury.api.self_ordering import add_customer_items, get_customer_order, get_order_status, get_ordering_context
from ury.ury.api.test_ordering_device import DEVICE_ID, DeviceCase
from ury.ury.api.test_self_ordering_table import TABLE, SelfOrderingCase, table_row
from ury.ury.doctype.ury_order.ury_order import cancel_order, split_bill, table_transfer
from ury.ury_pos.api import merge_bills


def occupied(table=TABLE):
	return frappe.db.get_value("URY Table", table, "occupied")


def printed(invoice):
	return frappe.db.get_value("POS Invoice", invoice, "invoice_printed")


class SplitMixin:
	"""The guests ordered 2 x food and 1 x alcohol on their phone; the bill is split in two (or three)."""

	def make_split(self, parts=2):
		self.staff_open()
		self.session = self.scan()
		self.source = add_customer_items(
			self.session, [{"item": FOOD_ITEM, "qty": 2}, {"item": ALCOHOL_ITEM, "qty": 1}], 1
		)["invoice"]
		self.sibling = self.move(ALCOHOL_ITEM)
		self.third = self.move(FOOD_ITEM) if parts == 3 else None
		frappe.db.commit()
		self.assertEqual(occupied(), 1)

	def move(self, item):
		row = frappe.get_all("POS Invoice Item", filters={"parent": self.source, "item_code": item}, pluck="name")[0]
		with as_user(CASHIER):
			return split_bill(self.source, [{"name": row, "qty": 1}])["new_invoice"]

	def assert_held(self, table=TABLE):
		self.assertEqual(occupied(table), 1, "the table is still taken")
		self.assertTrue(table_row(table)["self_order_open"], "self ordering is still open")

	def assert_free(self, table=TABLE):
		self.assertEqual(occupied(table), 0, "the table is free")
		self.assertFalse(table_row(table)["self_order_open"], "self ordering is closed")


class TestPrinting(SplitMixin, SelfOrderingCase):
	def test_printing_one_part_keeps_the_table(self):
		self.make_split()
		print_bill(self.source, CASHIER)
		self.assertEqual(printed(self.source), 1)
		self.assert_held()

	def test_printing_the_last_part_frees_the_table(self):
		self.make_split()
		print_bill(self.source, CASHIER)
		print_bill(self.sibling, CASHIER)
		self.assert_free()

	def test_the_order_of_printing_does_not_matter(self):
		self.make_split()
		print_bill(self.sibling, CASHIER)
		self.assert_held()
		print_bill(self.source, CASHIER)
		self.assert_free()

	def test_with_three_parts_only_the_last_one_frees_it(self):
		self.make_split(parts=3)
		print_bill(self.third, CASHIER)
		self.assert_held()
		print_bill(self.source, CASHIER)
		self.assert_held()
		print_bill(self.sibling, CASHIER)
		self.assert_free()

	def test_a_bill_that_was_not_split_frees_the_table_as_before(self):
		self.staff_open()
		invoice = place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLES[1])
		self.staff_open(TABLES[1])
		print_bill(invoice, CASHIER)
		self.assert_free(TABLES[1])

	def test_the_helper_that_all_the_print_paths_use(self):
		from ury.ury.doctype.ury_order.ury_order import unprinted_split_parts_on_table

		self.make_split()
		self.assertEqual(unprinted_split_parts_on_table(self.source), [self.sibling])
		self.assertEqual(unprinted_split_parts_on_table(self.sibling), [self.source])
		frappe.db.set_value("POS Invoice", self.sibling, "invoice_printed", 1, update_modified=False)
		self.assertEqual(unprinted_split_parts_on_table(self.source), [])

	def test_a_part_that_moved_to_another_table_does_not_hold_this_one(self):
		from ury.ury.doctype.ury_order.ury_order import unprinted_split_parts_on_table

		self.make_split()
		frappe.db.set_value("POS Invoice", self.sibling, "restaurant_table", TABLES[2], update_modified=False)
		self.assertEqual(unprinted_split_parts_on_table(self.source), [])


class TestPaying(SplitMixin, SelfOrderingCase):
	def test_paying_the_first_part_keeps_the_table_until_the_other_is_printed(self):
		self.make_split()
		pay_order(self.source, CASHIER)
		self.assert_held()
		print_bill(self.sibling, CASHIER)
		self.assert_free()


class TestCancelling(SplitMixin, SelfOrderingCase):
	def cancel(self, invoice):
		with as_user(CASHIER):
			cancel_order(invoice, "test")

	def test_cancelling_one_part_keeps_the_table(self):
		self.make_split()
		self.cancel(self.sibling)
		self.assert_held()

	def test_cancelling_the_last_part_frees_it(self):
		self.make_split()
		self.cancel(self.sibling)
		self.cancel(self.source)
		self.assert_free()

	def test_cancelling_a_printed_part_while_the_other_is_not_printed_keeps_the_table(self):
		self.make_split()
		print_bill(self.source, CASHIER)
		self.cancel(self.source)
		self.assert_held()

	def test_cancelling_the_unprinted_part_when_the_other_is_printed_frees_the_table(self):
		self.make_split()
		print_bill(self.source, CASHIER)
		self.cancel(self.sibling)
		self.assert_free()


class TestTheRemainingPartAfterTheOriginalIsCancelled(SplitMixin, SelfOrderingCase):
	"""The bill that was split off must stay usable when the bill it was split from is cancelled: dishes can be added
	to it and it can be paid. (ERPNext refuses to save a bill that still links to a cancelled bill.)"""

	def test_the_remaining_part_can_be_paid(self):
		self.make_split()
		with as_user(CASHIER):
			cancel_order(self.source, "test")
		doc = pay_order(self.sibling, CASHIER)
		self.assertEqual(doc.docstatus, 1)

	def test_why_it_had_to_be_changed_a_link_to_the_cancelled_bill_makes_payment_fail(self):
		self.make_split()
		with as_user(CASHIER):
			cancel_order(self.source, "test")
		frappe.db.set_value("POS Invoice", self.sibling, "custom_split_from", self.source, update_modified=False)
		with self.assertRaises(Exception) as caught:
			pay_order(self.sibling, CASHIER)
		self.assertIn("cancelled", str(caught.exception).lower())


class TestMoving(SplitMixin, SelfOrderingCase):
	def test_moving_one_part_keeps_the_old_table(self):
		self.make_split()
		with as_user(MANAGER):
			table_transfer(TABLE, TABLES[2], self.sibling)
		self.assert_held(TABLE)
		self.assertEqual(occupied(TABLES[2]), 1)
		self.assertEqual(frappe.db.get_value("POS Invoice", self.sibling, "restaurant_table"), TABLES[2])

	def test_a_bill_that_was_not_split_frees_the_old_table_as_before(self):
		self.staff_open(TABLES[1])
		invoice = place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLES[1])
		with as_user(MANAGER):
			table_transfer(TABLES[1], TABLES[2], invoice)
		self.assert_free(TABLES[1])


class TestMerging(SplitMixin, SelfOrderingCase):
	def test_two_parts_merged_again_free_the_table_when_printed(self):
		self.make_split()
		with as_user(CASHIER):
			self.assertEqual(merge_bills(self.source, self.sibling)["status"], "success")
		# merging closes self ordering for the phones (the guests are going to pay together)
		print_bill(self.source, CASHIER)
		self.assertEqual(occupied(), 0)

	def test_two_merged_parts_do_not_free_the_table_while_a_third_is_not_printed(self):
		self.make_split(parts=3)
		with as_user(CASHIER):
			self.assertEqual(merge_bills(self.source, self.sibling)["status"], "success")
		print_bill(self.source, CASHIER)
		self.assertEqual(occupied(), 1)
		print_bill(self.third, CASHIER)
		self.assertEqual(occupied(), 0)


class TestTheSessionFollowsTheOpenPart(SplitMixin, SelfOrderingCase):
	def order(self, session, quantity=1):
		return add_customer_items(session, [{"item": FOOD_ITEM, "qty": quantity}])

	def test_after_the_bill_of_the_session_is_printed_it_orders_on_the_other_part(self):
		self.make_split()
		print_bill(self.source, CASHIER)
		order = self.order(self.session)
		self.assertEqual(order["invoice"], self.sibling)
		self.assertEqual(frappe.db.get_value("URY Ordering Session", {"ordering_profile": "SELF-ORDER-TEST"}, "invoice"), self.sibling)
		self.assertEqual(printed(self.source), 1)

	def test_the_page_is_shown_the_part_it_follows(self):
		self.make_split()
		print_bill(self.source, CASHIER)
		shown = get_customer_order(self.session)
		self.assertEqual(shown["invoice"], self.sibling)
		self.assertTrue(shown["split"])
		self.assertEqual(get_order_status(self.session)["invoice"], self.sibling)

	def test_when_the_other_part_is_printed_too_the_table_closes_and_the_session_ends(self):
		self.make_split()
		print_bill(self.source, CASHIER)
		self.order(self.session)
		print_bill(self.sibling, CASHIER)
		self.refused("Table closed", self.order, self.session)

	def test_with_three_parts_it_follows_the_one_that_is_left(self):
		self.make_split(parts=3)
		print_bill(self.source, CASHIER)
		print_bill(self.third, CASHIER)
		self.assertEqual(self.order(self.session)["invoice"], self.sibling)

	def test_a_paid_part_is_followed_from_too(self):
		self.make_split()
		pay_order(self.source, CASHIER)
		self.assertEqual(self.order(self.session)["invoice"], self.sibling)

	def test_a_cancelled_part_is_followed_from_too(self):
		self.make_split()
		with as_user(CASHIER):
			cancel_order(self.source, "test")
		self.assertEqual(self.order(self.session)["invoice"], self.sibling)

	def test_the_part_that_stays_does_not_point_at_the_cancelled_bill(self):
		# ERPNext refuses to save a bill that links to a cancelled one: the part could take no dishes
		self.make_split()
		with as_user(CASHIER):
			cancel_order(self.source, "test")
		self.assertFalse(frappe.db.get_value("POS Invoice", self.sibling, "custom_split_from"))
		self.assertEqual(frappe.db.get_value("POS Invoice", self.sibling, "custom_split_group"), frappe.db.get_value("POS Invoice", self.source, "custom_split_group"))

	def test_a_bill_that_was_not_split_ends_the_session_as_before(self):
		self.staff_open()
		session = self.scan()
		invoice = add_customer_items(session, [{"item": FOOD_ITEM, "qty": 1}])["invoice"]
		frappe.db.set_value("POS Invoice", invoice, "invoice_printed", 1, update_modified=False)
		self.refused("Order closed", self.order, session)

	def test_a_phone_that_scans_now_orders_on_the_open_part(self):
		self.make_split()
		print_bill(self.source, CASHIER)
		self.assertEqual(self.order(self.scan())["invoice"], self.sibling)


class TestTheTabletFollowsToo(SplitMixin, DeviceCase):
	def test_a_tablet_goes_on_ordering_and_keeps_the_table_open(self):
		self.make_split()
		credential = self.issue()["credential"]
		context = get_ordering_context(device_id=DEVICE_ID, device_credential=credential)
		session = context["session"]
		# the tablet orders on the order of the table, then the bill of that order is printed
		first = add_customer_items(session, [{"item": FOOD_ITEM, "qty": 1}])["invoice"]
		print_bill(first, CASHIER)
		self.assertEqual(self.status(credential)["state"], "open")
		order = add_customer_items(session, [{"item": FOOD_ITEM, "qty": 1}])
		self.assertNotEqual(order["invoice"], first)
		self.assertEqual(printed(order["invoice"]), 0)
		other = self.sibling if order["invoice"] != self.sibling else self.source
		print_bill(order["invoice"], CASHIER)
		if printed(other) == 0:
			print_bill(other, CASHIER)
		self.assertEqual(self.status(credential)["state"], "table_closed")
