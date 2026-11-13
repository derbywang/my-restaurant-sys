"""Self ordering at a table: the staff open the table, the guests order, the table closes by itself.

A guest scans the QR code stuck on the table; the order goes through only while the branch has an
opened and not yet closed shift and the staff have opened that table. The table closes when the
bill is printed, the table is released (paid, cancelled), transferred, the shift is closed, or the
profile's time is up. Sessions of an earlier opening stop being valid. Run on the test site only.
"""

import json
from unittest import mock
from datetime import timedelta

import frappe
from frappe.utils import add_to_date, now_datetime

from ury.setup.test_site import (
	ALCOHOL_ITEM,
	BRANCH,
	CAPTAIN,
	CASHIER,
	CUSTOMER,
	FOOD_ITEM,
	MANAGER,
	POS_PROFILE,
	RESTAURANT,
	TABLES,
	URYFlowTestCase,
	as_user,
	close_shift,
	open_pos,
	pay_order,
	place_order,
	print_bill,
)
from ury.ury.api.pos_permissions import get_pos_permissions
from ury.ury.api.self_ordering import (
	add_customer_items,
	branch_is_open,
	close_table_for_ordering,
	generate_qr_token,
	get_customer_menu,
	get_customer_order,
	get_order_status,
	get_ordering_context,
	open_table_for_ordering,
	_customer_menu,
	preview_customer_cart,
)
from ury.ury.doctype.ury_order.ury_order import cancel_order, table_transfer
from ury.ury_pos.api import merge_bills

PROFILE = "SELF-ORDER-TEST"
TABLE = TABLES[0]
OTHER_TABLE = TABLES[1]


def titles():
	return [m.get("title") for m in frappe.local.message_log]


def table_row(table=TABLE):
	return frappe.db.get_value(
		"URY Table",
		table,
		["self_order_open", "self_order_opened_at", "self_order_opened_by", "self_order_opening"],
		as_dict=True,
	)


class SelfOrderingCase(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		self.opening = open_pos(CASHIER)
		self._make_profile()
		self.addCleanup(self._clean)
		frappe.local.message_log = []

	def _make_profile(self):
		self._clean()
		doc = frappe.get_doc(
			{
				"doctype": "URY Self Ordering Profile",
				"profile_name": PROFILE,
				"restaurant": RESTAURANT,
				"branch": BRANCH,
				"pos_profile": POS_PROFILE,
				"default_customer": CUSTOMER,
				"enabled": 1,
				"enable_qr_table_ordering": 1,
				"enable_device_ordering": 1,
				"allow_add_to_running_table": 1,
				"enable_pay_at_counter": 1,
				"qr_signing_secret": "self-order-test-secret",
				"table_open_minutes": 240,
			}
		)
		doc.name = PROFILE
		doc.insert(ignore_permissions=True)
		frappe.db.commit()

	def _clean(self):
		frappe.db.delete("URY Ordering Session", {"ordering_profile": PROFILE})
		if frappe.db.exists("URY Self Ordering Profile", PROFILE):
			frappe.delete_doc("URY Self Ordering Profile", PROFILE, force=True, ignore_permissions=True)
		for table in TABLES:
			frappe.db.set_value(
				"URY Table",
				table,
				{"self_order_open": 0, "self_order_opened_at": None, "self_order_opened_by": None, "self_order_opening": None},
			)
		frappe.db.commit()

	# --- what a guest does ------------------------------------------------

	def scan(self, table=TABLE):
		with as_user("Administrator"):
			token = generate_qr_token(PROFILE, table)
		return get_ordering_context(token=token)["session"]

	def order(self, session, quantity=1):
		return add_customer_items(session, [{"item": FOOD_ITEM, "qty": quantity}])

	def refused(self, title, call, *args, exc=(frappe.ValidationError, frappe.PermissionError), **kwargs):
		frappe.local.message_log = []
		with self.assertRaises(exc):
			call(*args, **kwargs)
		self.assertIn(title, titles())

	# --- what the staff do ------------------------------------------------

	def staff_open(self, table=TABLE, user=CASHIER):
		with as_user(user):
			return open_table_for_ordering(table)

	def staff_close(self, table=TABLE, user=CASHIER):
		with as_user(user):
			return close_table_for_ordering(table)


class TestOpeningHours(SelfOrderingCase):
	"""The branch must have an opened shift that has not been closed (the date does not matter)."""

	def test_an_opened_shift_is_enough(self):
		self.assertTrue(branch_is_open(BRANCH))

	def test_a_shift_opened_yesterday_and_not_closed_is_still_open(self):
		# past midnight, or the staff forgot to close yesterday's shift
		yesterday = add_to_date(now_datetime(), days=-1)
		frappe.db.set_value(
			"POS Opening Entry",
			self.opening.name,
			{"posting_date": yesterday.date(), "period_start_date": yesterday},
			update_modified=False,
		)
		self.assertTrue(branch_is_open(BRANCH))
		self.staff_open()
		self.assertTrue(self.order(self.scan()))

	def test_another_branchs_shift_does_not_count(self):
		self.assertFalse(branch_is_open("a branch nobody opened"))
		self.assertFalse(branch_is_open(None))

	def test_when_the_shift_is_closed_the_branch_is_closed(self):
		close_shift(self.opening)
		self.assertFalse(branch_is_open(BRANCH))

	def test_without_an_open_shift_nobody_can_scan_in(self):
		self.staff_open()
		close_shift(self.opening)
		self.refused("Store closed", self.scan)

	def test_without_an_open_shift_a_table_cannot_be_opened(self):
		close_shift(self.opening)
		self.refused("Store closed", self.staff_open)

	def test_a_session_started_before_the_shift_was_closed_stops_working(self):
		self.staff_open()
		session = self.scan()
		close_shift(self.opening)
		self.refused("Store closed", self.order, session)


class TestTheTableMustBeOpen(SelfOrderingCase):
	def test_a_table_that_is_not_open_cannot_be_ordered_from(self):
		self.refused("Table closed", self.scan)

	def test_after_the_staff_open_it_the_guests_can_order(self):
		self.staff_open()
		session = self.scan()
		order = self.order(session)
		self.assertTrue(order["invoice"])
		self.assertEqual(order["table"], TABLE)
		self.assertTrue(get_customer_menu(session)["items"])

	def test_closing_it_ends_the_session(self):
		self.staff_open()
		session = self.scan()
		self.staff_close()
		self.refused("Table closed", self.order, session)
		self.refused("Table closed", get_customer_menu, session)

	def test_the_session_of_the_guests_before_is_not_valid_after_it_is_opened_again(self):
		self.staff_open()
		old_session = self.scan()
		self.staff_close()
		self.staff_open()
		self.refused("Table closed", self.order, old_session)
		new_session = self.scan()
		self.assertTrue(self.order(new_session))

	def test_opening_again_without_closing_also_starts_over(self):
		self.staff_open()
		old_session = self.scan()
		self.staff_open()
		self.refused("Table closed", self.order, old_session)

	def test_after_the_time_is_up_the_table_is_closed_by_itself(self):
		self.staff_open()
		session = self.scan()
		long_ago = add_to_date(now_datetime(), minutes=-241)
		frappe.db.set_value("URY Table", TABLE, "self_order_opened_at", long_ago, update_modified=False)
		self.refused("Table closed", self.order, session)
		self.refused("Table closed", self.scan)

	def test_a_guest_can_still_read_the_order_after_the_table_was_closed(self):
		self.staff_open()
		session = self.scan()
		self.order(session)
		self.staff_close()
		self.assertEqual(len(get_customer_order(session)["items"]), 1)
		self.assertFalse(get_order_status(session)["table_open"])

	def test_the_status_says_the_table_is_open(self):
		self.staff_open()
		session = self.scan()
		self.assertTrue(get_order_status(session)["table_open"])

	def test_a_table_opened_is_not_the_other_table(self):
		self.staff_open(TABLE)
		self.refused("Table closed", self.scan, OTHER_TABLE)


class TestTheTableClosesByItself(SelfOrderingCase):
	def _open_with_order(self):
		self.staff_open()
		session = self.scan()
		invoice = self.order(session)["invoice"]
		self.assertTrue(table_row()["self_order_open"])
		return session, invoice

	def test_when_the_bill_is_printed(self):
		session, invoice = self._open_with_order()
		print_bill(invoice, CASHIER)
		self.assertFalse(table_row()["self_order_open"])
		self.refused("Table closed", self.order, session)

	def test_when_the_order_is_paid(self):
		session, invoice = self._open_with_order()
		print_bill(invoice, CASHIER)
		pay_order(invoice, CASHIER)
		self.assertFalse(table_row()["self_order_open"])

	def test_when_the_order_is_cancelled(self):
		session, invoice = self._open_with_order()
		with as_user(CASHIER):
			cancel_order(invoice, "test")
		self.assertFalse(table_row()["self_order_open"])
		self.refused("Table closed", self.order, session)

	def test_when_the_order_moves_to_another_table(self):
		session, invoice = self._open_with_order()
		with as_user(MANAGER):
			table_transfer(TABLE, TABLES[2], invoice)
		self.assertFalse(table_row(TABLE)["self_order_open"])
		self.refused("Table closed", self.order, session)

	def test_when_the_shift_is_closed(self):
		self.staff_open(TABLE)
		self.staff_open(OTHER_TABLE)
		close_shift(self.opening)
		self.assertFalse(table_row(TABLE)["self_order_open"])
		self.assertFalse(table_row(OTHER_TABLE)["self_order_open"])

	def test_the_other_tables_stay_open(self):
		self.staff_open(TABLE)
		self.staff_open(OTHER_TABLE)
		self.staff_close(TABLE)
		self.assertTrue(table_row(OTHER_TABLE)["self_order_open"])


class TestAfterTheBillIsPrinted(SelfOrderingCase):
	def test_a_printed_order_takes_no_more_dishes_even_if_the_table_is_still_open(self):
		self.staff_open()
		session = self.scan()
		invoice = self.order(session)["invoice"]
		# printed in the database only: the table was not released (as a stale call would find it)
		frappe.db.set_value("POS Invoice", invoice, "invoice_printed", 1, update_modified=False)
		self.refused("Order closed", self.order, session)
		self.assertEqual(frappe.db.count("POS Invoice Item", {"parent": invoice}), 1)

	def test_before_it_is_printed_the_guests_can_add_dishes(self):
		self.staff_open()
		session = self.scan()
		invoice = self.order(session)["invoice"]
		self.assertEqual(self.order(session)["invoice"], invoice)
		self.assertEqual(frappe.db.count("POS Invoice Item", {"parent": invoice}), 2)

	def test_an_order_that_is_gone_is_closed_not_started_again(self):
		self.staff_open()
		session = self.scan()
		invoice = self.order(session)["invoice"]
		frappe.db.set_value("POS Invoice", invoice, "docstatus", 2, update_modified=False)
		self.refused("Order closed", self.order, session)
		self.assertEqual(frappe.db.count("POS Invoice", {"docstatus": 0, "restaurant_table": TABLE}), 0)

	def test_a_table_whose_bill_is_printed_can_be_opened_again_for_the_next_guests(self):
		invoice = place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLE)
		print_bill(invoice, CASHIER)  # printing releases the table: it is Available again
		self.assertEqual(frappe.db.get_value("URY Table", TABLE, "occupied"), 0)
		self.assertTrue(self.staff_open()["tables"])
		self.assertTrue(table_row()["self_order_open"])


class TestWhoMayOpenATable(SelfOrderingCase):
	def test_anyone_who_takes_orders_may(self):
		for user in (CASHIER, CAPTAIN, MANAGER):
			self.staff_close()
			result = self.staff_open(user=user)
			self.assertEqual(result["tables"], [TABLE])
			self.assertEqual(table_row()["self_order_opened_by"], user)

	def test_it_is_open_for_four_hours(self):
		result = self.staff_open()
		self.assertEqual(result["expires_at"] - result["opened_at"], timedelta(minutes=240))

	def test_a_user_without_a_pos_role_may_not(self):
		user = "norole-so@test.local"
		if not frappe.db.exists("User", user):
			frappe.get_doc(
				{"doctype": "User", "email": user, "first_name": "No Role", "send_welcome_email": 0, "roles": []}
			).insert(ignore_permissions=True)
		with self.assertRaises(frappe.PermissionError):
			self.staff_open(user=user)
		with self.assertRaises(frappe.PermissionError):
			self.staff_close(user=user)
		self.assertFalse(table_row()["self_order_open"])

	def test_a_guest_may_not(self):
		with self.assertRaises(frappe.PermissionError):
			self.staff_open(user="Guest")

	def test_a_take_away_table_cannot_be_opened(self):
		frappe.db.set_value("URY Table", TABLE, "is_take_away", 1)
		self.addCleanup(frappe.db.set_value, "URY Table", TABLE, "is_take_away", 0)
		with self.assertRaises(frappe.ValidationError):
			self.staff_open()

	def test_a_table_of_another_branch_may_not(self):
		original = frappe.db.get_value("URY Table", TABLE, "branch")
		frappe.db.set_value("URY Table", TABLE, "branch", "somewhere else", update_modified=False)
		self.addCleanup(frappe.db.set_value, "URY Table", TABLE, "branch", original)
		with self.assertRaises(frappe.PermissionError):
			self.staff_open(user=CAPTAIN)

	def test_a_table_with_the_order_of_a_waiter_can_be_opened_and_the_guests_add_to_it(self):
		invoice = place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLE)
		self.staff_open()
		session = self.scan()
		self.assertEqual(self.order(session)["invoice"], invoice)

	def test_a_branch_without_a_self_ordering_profile_cannot_open_tables(self):
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, "enabled", 0)
		with self.assertRaises(frappe.ValidationError):
			self.staff_open()

	def test_the_pos_permission_map_says_who_may(self):
		for user in (CASHIER, CAPTAIN, MANAGER, "Administrator"):
			with as_user(user):
				self.assertTrue(get_pos_permissions()["open_self_order"], user)
		user = "norole-so@test.local"
		if not frappe.db.exists("User", user):
			frappe.get_doc(
				{"doctype": "User", "email": user, "first_name": "No Role", "send_welcome_email": 0, "roles": []}
			).insert(ignore_permissions=True)
		with as_user(user):
			self.assertFalse(get_pos_permissions()["open_self_order"])


# --- the guests' order and the staff -----------------------------------------------------------

from ury.ury.api import self_ordering
from ury.ury.doctype.ury_order.ury_order import get_table_order_context


def tickets_since(invoice, before):
	"""{ticket type: [(item, quantity, comments, cancelled_qty)]} of the kitchen tickets of the order made after `before`."""
	result = {}
	for ticket in frappe.get_all("URY KOT", filters={"invoice": invoice}, fields=["name", "type"], order_by="creation"):
		if ticket.name in before:
			continue
		rows = frappe.get_all(
			"URY KOT Items",
			filters={"parent": ticket.name},
			fields=["item", "quantity", "comments", "cancelled_qty"],
		)
		result.setdefault(ticket.type, []).extend(
			(row.item, int(row.quantity), row.comments or "", int(row.cancelled_qty or 0)) for row in rows
		)
	return result


def ticket_names(invoice):
	return set(frappe.get_all("URY KOT", filters={"invoice": invoice}, pluck="name"))


class TestTheGuestsNoteReachesTheKitchen(SelfOrderingCase):
	def _note(self, session, text, quantity=1):
		return add_customer_items(session, [{"item": FOOD_ITEM, "qty": quantity, "comment": text}])

	def test_the_note_of_a_dish_is_on_the_kitchen_ticket(self):
		self.staff_open()
		session = self.scan()
		invoice = self._note(session, "わさび抜き")["invoice"]
		self.assertEqual(tickets_since(invoice, set())["New Order"], [(FOOD_ITEM, 1, "わさび抜き", 0)])

	def test_the_same_dish_again_sends_only_what_was_added_with_its_own_note(self):
		self.staff_open()
		session = self.scan()
		invoice = self._note(session, "わさび抜き")["invoice"]
		before = ticket_names(invoice)
		self._note(session, "大盛り", quantity=2)
		tickets = tickets_since(invoice, before)
		self.assertEqual(sum(tickets.values(), []), [(FOOD_ITEM, 2, "大盛り", 0)])
		self.assertNotIn("Partially cancelled", tickets)

	def test_the_same_dish_without_a_note_is_not_sent_twice(self):
		self.staff_open()
		session = self.scan()
		invoice = self._note(session, "")["invoice"]
		before = ticket_names(invoice)
		self._note(session, "")
		sent = sum(tickets_since(invoice, before).values(), [])
		self.assertEqual([(item, quantity) for item, quantity, _c, _x in sent], [(FOOD_ITEM, 1)])


class TestTheWaiterTakesOverTheGuestsOrder(SelfOrderingCase):
	"""A waiter adds to and changes an order the guests placed, like any order; only the cashier takes dishes back."""

	def setUp(self):
		super().setUp()
		original = frappe.db.get_value("POS Profile", POS_PROFILE, "remove_items")
		self.addCleanup(self._switch, original)
		self._switch(1)
		self.staff_open(user=CASHIER)  # not the captain: he did not open the table
		self.session = self.scan()
		self.invoice = add_customer_items(self.session, [{"item": FOOD_ITEM, "qty": 2}])["invoice"]
		frappe.db.commit()

	def _switch(self, value):
		frappe.db.set_value("POS Profile", POS_PROFILE, "remove_items", value)
		frappe.db.commit()
		frappe.clear_document_cache("POS Profile", POS_PROFILE)

	def _quantity(self):
		return frappe.db.get_value("POS Invoice Item", {"parent": self.invoice, "item_code": FOOD_ITEM}, "qty")

	def test_the_order_is_the_order_of_the_staff_who_opened_the_table(self):
		self.assertEqual(frappe.db.get_value("POS Invoice", self.invoice, "waiter"), CASHIER)
		self.assertEqual(frappe.db.get_value("POS Invoice", self.invoice, "custom_order_source"), "QR Table")

	def test_a_waiter_who_did_not_open_the_table_sees_the_order_and_may_change_it(self):
		with as_user(CAPTAIN):
			context = get_table_order_context(TABLE)
		self.assertEqual(context["order"]["name"], self.invoice)
		self.assertTrue(context["permissions"]["view"])
		self.assertTrue(context["permissions"]["modify"])

	def test_he_adds_a_dish(self):
		place_order(CAPTAIN, [(FOOD_ITEM, 3)], table=TABLE, invoice=self.invoice)
		self.assertEqual(self._quantity(), 3)

	def test_he_cannot_take_a_dish_back(self):
		with self.assertRaises(frappe.PermissionError):
			place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLE, invoice=self.invoice)
		frappe.db.rollback()
		self.assertEqual(self._quantity(), 2)
		with as_user(CAPTAIN):
			permissions = get_table_order_context(TABLE)["permissions"]
		self.assertFalse(permissions["reduce_items"])
		self.assertFalse(permissions["remove_items"])

	def test_the_cashier_can_take_a_dish_back(self):
		place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLE, invoice=self.invoice)
		self.assertEqual(self._quantity(), 1)

	def test_the_guests_can_still_add_after_the_waiter_did(self):
		place_order(CAPTAIN, [(FOOD_ITEM, 3)], table=TABLE, invoice=self.invoice)
		order = add_customer_items(self.session, [{"item": FOOD_ITEM, "qty": 1}])
		self.assertEqual(order["invoice"], self.invoice)

	def test_an_order_of_another_user_is_open_to_a_captain_of_the_branch(self):
		"""Not only the guests' orders: no order has an owner to protect (2026-11, see test_captain_access)."""
		invoice = place_order(MANAGER, [(FOOD_ITEM, 1)], table=TABLES[2])
		frappe.db.set_value("POS Invoice", invoice, "waiter", MANAGER)
		with as_user(CAPTAIN):
			context = get_table_order_context(TABLES[2])
		self.assertTrue(context["permissions"]["view"])
		self.assertFalse(context["permissions"]["reduce_items"])


class TestWhatTheGuestsSeeWhenTheOrderIsOver(SelfOrderingCase):
	def _ordered(self):
		self.staff_open()
		session = self.scan()
		invoice = self.order(session)["invoice"]
		return session, invoice

	def test_while_it_is_open(self):
		session, _invoice = self._ordered()
		self.assertEqual(get_order_status(session)["order_state"], "open")
		self.assertEqual(get_customer_order(session)["state"], "open")

	def test_when_the_bill_is_printed(self):
		session, invoice = self._ordered()
		print_bill(invoice, CASHIER)
		self.assertEqual(get_order_status(session)["order_state"], "billed")
		order = get_customer_order(session)
		self.assertEqual(order["state"], "billed")
		self.assertTrue(order["items"])  # the guests can still see what they ordered

	def test_when_the_order_is_cancelled(self):
		session, invoice = self._ordered()
		with as_user(CASHIER):
			cancel_order(invoice, "test")
		self.assertEqual(get_order_status(session)["order_state"], "cancelled")
		order = get_customer_order(session)
		self.assertEqual(order["state"], "cancelled")
		self.assertEqual(order["items"], [])
		self.assertFalse(get_order_status(session)["table_open"])
		self.refused("Table closed", self.order, session)

	def test_when_the_order_is_paid(self):
		session, invoice = self._ordered()
		print_bill(invoice, CASHIER)
		pay_order(invoice, CASHIER)
		self.assertEqual(get_order_status(session)["order_state"], "paid")
		self.assertEqual(get_customer_order(session)["items"], [])

	def test_before_any_order(self):
		self.staff_open()
		session = self.scan()
		self.assertEqual(get_order_status(session)["order_state"], "none")
		self.assertEqual(get_customer_order(session)["state"], "none")


class TestAGuestCannotOrderOnACancelledOrder(SelfOrderingCase):
	"""The cashier cancels the order of the guests (cancel_order does not touch the session). The same session
	orders again: refused, the cancelled order stays as it was, and no new order is started."""

	def _cancelled(self):
		self.staff_open()
		session = self.scan()
		invoice = self.order(session)["invoice"]
		with as_user(CASHIER):
			cancel_order(invoice, "test")
		return session, invoice

	def _state(self, invoice):
		return (
			frappe.db.get_value("POS Invoice", invoice, ["docstatus", "grand_total"]),
			frappe.get_all("POS Invoice Item", filters={"parent": invoice}, fields=["item_code", "qty"], order_by="idx"),
			sorted(frappe.get_all("POS Invoice", filters={"restaurant_table": TABLE}, pluck="name")),
		)

	def test_the_table_is_closed_so_the_session_is_refused(self):
		session, invoice = self._cancelled()
		before = self._state(invoice)
		self.assertEqual(frappe.db.get_value("URY Ordering Session", {"invoice": invoice}, "status"), "Active")
		self.refused("Table closed", add_customer_items, session, [{"item": FOOD_ITEM, "qty": 1}])
		self.assertEqual(self._state(invoice), before)

	def test_even_when_the_table_is_opened_again(self):
		session, invoice = self._cancelled()
		before = self._state(invoice)
		self.staff_open()
		# the strictest case: the old session belongs to the new opening; only the cancelled order is left to stop it
		frappe.db.set_value(
			"URY Ordering Session", {"invoice": invoice}, "table_opening", frappe.db.get_value("URY Table", TABLE, "self_order_opening")
		)
		frappe.db.commit()
		self.refused("Order closed", add_customer_items, session, [{"item": FOOD_ITEM, "qty": 1}])
		self.assertEqual(self._state(invoice), before)


class TestTheGuestsCannotTakeDishesBack(SelfOrderingCase):
	"""Whatever the guests send, the order only grows; a mistake is for the staff (the cashier) to correct."""

	# what the guests' interface may do; a new function that the guests can call must be added here on purpose
	GUEST_FUNCTIONS = {
		"get_ordering_context",
		"device_status",
		"get_customer_menu",
		"get_customer_product",
		"get_customer_order",
		"preview_customer_cart",
		"confirm_age",
		"add_customer_items",
		"request_bill",
		"get_order_status",
		"create_payment_request",
		"get_payment_status",
		"share_payment_link",
	}
	CHANGE_THE_ORDER = {"add_customer_items"}

	def test_the_functions_the_guests_can_call_are_the_known_ones(self):
		guest = {f.__name__ for f in frappe.guest_methods if f.__module__ == self_ordering.__name__}
		self.assertEqual(guest, self.GUEST_FUNCTIONS)

	def test_a_new_order_line_is_added_and_the_old_ones_stay(self):
		self.staff_open()
		session = self.scan()
		invoice = self.order(session, quantity=2)["invoice"]
		self.order(session, quantity=1)
		rows = frappe.get_all(
			"POS Invoice Item", filters={"parent": invoice}, fields=["item_code", "qty"], order_by="idx"
		)
		self.assertEqual([(r.item_code, int(r.qty)) for r in rows], [(FOOD_ITEM, 2), (FOOD_ITEM, 1)])

	def test_a_quantity_of_zero_or_less_is_refused_and_changes_nothing(self):
		self.staff_open()
		session = self.scan()
		invoice = self.order(session, quantity=2)["invoice"]
		for quantity in (0, -1, -2, "-1", "x", None):
			with self.assertRaises(frappe.ValidationError, msg=repr(quantity)):
				add_customer_items(session, [{"item": FOOD_ITEM, "qty": quantity}])
		rows = frappe.get_all("POS Invoice Item", filters={"parent": invoice}, fields=["qty"])
		self.assertEqual([int(r.qty) for r in rows], [2])

	def test_a_request_that_adds_and_subtracts_in_one_go_is_refused_as_a_whole(self):
		self.staff_open()
		session = self.scan()
		invoice = self.order(session, quantity=2)["invoice"]
		frappe.db.commit()  # as the request does; the refused one below is rolled back on its own
		with self.assertRaises(frappe.ValidationError):
			add_customer_items(session, [{"item": FOOD_ITEM, "qty": 3}, {"item": FOOD_ITEM, "qty": -3}])
		frappe.db.rollback()
		rows = frappe.get_all("POS Invoice Item", filters={"parent": invoice}, fields=["qty"])
		self.assertEqual([int(r.qty) for r in rows], [2])


class TestWhatThePosShows(SelfOrderingCase):
	"""`get_open_tables`: whether the POS offers the button, and which tables are open now."""

	def tables(self, user=CASHIER):
		with as_user(user):
			return self_ordering.get_open_tables()

	def test_the_button_is_offered_to_whoever_takes_orders_when_the_branch_has_a_profile(self):
		for user in (CASHIER, CAPTAIN, MANAGER):
			self.assertTrue(self.tables(user)["enabled"], user)

	def test_it_is_not_offered_without_a_profile_or_with_the_tables_switched_off(self):
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, "enable_qr_table_ordering", 0)
		self.assertFalse(self.tables()["enabled"])
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, {"enable_qr_table_ordering": 1, "enabled": 0})
		self.assertFalse(self.tables()["enabled"])

	def test_it_is_not_offered_to_a_user_who_does_not_take_orders_or_to_a_guest(self):
		self.assertEqual(self.tables("Guest"), {"enabled": False, "store_open": False, "tables": [], "blocked": []})

	def test_the_open_tables_are_listed_with_the_time_they_were_opened(self):
		self.staff_open(TABLE, user=CAPTAIN)
		listed = self.tables()["tables"]
		self.assertEqual([row["table"] for row in listed], [TABLE])
		self.assertEqual(listed[0]["opened_by"], CAPTAIN)
		self.assertTrue(listed[0]["opened_at"] and listed[0]["expires_at"])

	def test_a_table_that_is_closed_or_timed_out_is_not_listed(self):
		self.staff_open(TABLE)
		self.staff_open(OTHER_TABLE)
		self.staff_close(TABLE)
		frappe.db.set_value(
			"URY Table", OTHER_TABLE, "self_order_opened_at", add_to_date(now_datetime(), minutes=-241), update_modified=False
		)
		self.assertEqual(self.tables()["tables"], [])

	def test_the_store_state_is_given_so_the_pos_can_say_why_a_table_cannot_be_opened(self):
		self.assertTrue(self.tables()["store_open"])
		close_shift(self.opening)
		self.assertFalse(self.tables()["store_open"])


class TestAsARealGuest(SelfOrderingCase):
	"""The customer page is used by nobody who is logged in. Every call below is made as Guest, which is
	what the browser of a guest is; the tests above run as the administrator and would not notice a
	missing permission."""

	def as_guest(self, call, *args, **kwargs):
		with as_user("Guest"):
			return call(*args, **kwargs)

	def scan_as_guest(self, table=TABLE):
		with as_user("Administrator"):
			token = generate_qr_token(PROFILE, table)
		return self.as_guest(get_ordering_context, token=token)["session"]

	def test_the_whole_way_from_the_code_to_the_order(self):
		self.staff_open()
		session = self.scan_as_guest()
		menu = self.as_guest(get_customer_menu, session)
		self.assertTrue(menu["items"])
		product = self.as_guest(self_ordering.get_customer_product, session, FOOD_ITEM)
		self.assertEqual(product["item_code"], FOOD_ITEM)
		order = self.as_guest(add_customer_items, session, [{"item": FOOD_ITEM, "qty": 1, "comment": "わさび抜き"}])
		self.assertTrue(order["invoice"])
		self.assertEqual(self.as_guest(get_customer_order, session)["state"], "open")
		self.assertTrue(self.as_guest(get_order_status, session)["table_open"])

	def test_the_guest_adds_to_the_order_a_waiter_started(self):
		invoice = place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLE)
		frappe.db.commit()
		self.staff_open()
		session = self.scan_as_guest()
		order = self.as_guest(add_customer_items, session, [{"item": FOOD_ITEM, "qty": 1}])
		self.assertEqual(order["invoice"], invoice)
		self.assertEqual(len(order["items"]), 2)
		# the amount next to "Total" on the ordering page: both dishes with the tax
		self.assertEqual(order["grand_total"], 2200, order)
		self.assertEqual(self.as_guest(get_customer_order, session)["grand_total"], 2200)


class TestOverHttp(SelfOrderingCase):
	"""The same calls the ordering page makes, over HTTP as a visitor without a login (GET for the code,
	the menu and the order, POST for the order), against the server that is running for the bench.

	The calls above are made in Python as the administrator or as Guest; they cannot show what only
	the HTTP layer does (the method of the request, the commit at the end of it, the answer a browser
	gets). Skipped when no server answers for the test site.
	"""

	BASE = "http://127.0.0.1:8000/api/method/ury.ury.api.self_ordering."

	def setUp(self):
		super().setUp()
		self.host = f"{frappe.local.site}:8000"

	def http(self, method, name, **params):
		import json as _json
		from urllib import error, parse, request as urlrequest

		url = self.BASE + name
		data = None
		if method == "GET":
			url += "?" + parse.urlencode(params)
		else:
			data = parse.urlencode(params).encode()
		req = urlrequest.Request(url, data=data, method=method, headers={"Host": self.host})
		try:
			with urlrequest.urlopen(req, timeout=20) as response:
				return response.status, _json.loads(response.read())
		except error.HTTPError as e:
			return e.code, _json.loads(e.read() or b"{}")
		except OSError:
			self.skipTest("no server answers on port 8000")

	def messages(self, body):
		"""The `title`s of the messages the server sent with an error."""
		return [_json.get("title") for _json in map(__import__("json").loads, __import__("json").loads(body.get("_server_messages", "[]")))]

	def test_a_table_that_is_not_open_is_refused_with_its_title(self):
		with as_user("Administrator"):
			token = generate_qr_token(PROFILE, TABLE)
		frappe.db.commit()
		status, body = self.http("GET", "get_ordering_context", token=token)
		self.assertEqual(status, 403)
		self.assertIn("Table closed", self.messages(body))

	def test_the_way_a_browser_goes_from_the_code_to_the_order(self):
		self.staff_open()
		frappe.db.commit()
		with as_user("Administrator"):
			token = generate_qr_token(PROFILE, TABLE)

		status, body = self.http("GET", "get_ordering_context", token=token)
		self.assertEqual(status, 200, body)
		session = body["message"]["session"]

		status, body = self.http("GET", "get_customer_menu", session=session)
		self.assertEqual(status, 200, body)
		self.assertTrue(body["message"]["items"])

		status, body = self.http("GET", "get_customer_order", session=session)
		self.assertEqual(status, 200, body)
		self.assertEqual(body["message"]["state"], "none")

		status, body = self.http(
			"POST", "add_customer_items", session=session, items=json.dumps([{"item": FOOD_ITEM, "qty": 1, "comment": "わさび抜き"}])
		)
		self.assertEqual(status, 200, body)
		invoice = body["message"]["invoice"]
		self.assertTrue(invoice)
		# what the page shows next to "Total": the amount of the order, with the tax (¥1,000 + 10%)
		self.assertEqual(body["message"]["grand_total"], 1100, body["message"])
		self.assertEqual([row["amount_incl_tax"] for row in body["message"]["items"]], [1100], body["message"])

		status, body = self.http("GET", "get_customer_menu", session=session)
		self.assertEqual({row["item"]: row["price_incl_tax"] for row in body["message"]["items"]}[FOOD_ITEM], 1100)
		status, body = self.http(
			"POST", "preview_customer_cart", session=session, items=json.dumps([{"item": ALCOHOL_ITEM, "qty": 2}])
		)
		self.assertEqual(status, 200, body)
		self.assertEqual((body["message"]["ordered_total"], body["message"]["rounded_total"]), (1100, 2200))

		status, body = self.http("GET", "get_customer_order", session=session)
		self.assertEqual(status, 200, body)
		self.assertEqual(body["message"]["invoice"], invoice)
		self.assertEqual(body["message"]["state"], "open")
		self.assertEqual(body["message"]["grand_total"], 1100, body["message"])


class TestOverHttpWhatAGetWrites(SelfOrderingCase):
	"""The server rolls a GET back at its end unless the code commits. The page asks the status and the order again and
	again with GET: a guest who is only looking must still keep the session alive (it ends after the idle minutes of
	the profile), which has to be committed by the code. Skipped when no server answers for the test site."""

	BASE = "http://127.0.0.1:8000/api/method/ury.ury.api.self_ordering."

	def setUp(self):
		super().setUp()
		self.host = f"{frappe.local.site}:8000"

	def get(self, name, **params):
		import json as _json
		from urllib import error, parse, request as urlrequest

		req = urlrequest.Request(self.BASE + name + "?" + parse.urlencode(params), method="GET", headers={"Host": self.host})
		try:
			with urlrequest.urlopen(req, timeout=20) as response:
				return response.status, _json.loads(response.read())
		except error.HTTPError as e:
			return e.code, _json.loads(e.read() or b"{}")
		except OSError:
			self.skipTest("no server answers on port 8000")

	def expires_at(self):
		frappe.db.rollback()  # see what the server committed
		return frappe.db.get_value("URY Ordering Session", {"ordering_profile": PROFILE}, "expires_at")

	def test_asking_the_order_again_and_again_keeps_the_session_alive(self):
		self.staff_open()
		frappe.db.commit()
		with as_user("Administrator"):
			token = generate_qr_token(PROFILE, TABLE)
		status, body = self.get("get_ordering_context", token=token)
		self.assertEqual(status, 200, body)
		session = body["message"]["session"]
		# the session was last active a while ago and ends in 5 minutes
		frappe.db.set_value(
			"URY Ordering Session",
			{"ordering_profile": PROFILE},
			{"last_activity": add_to_date(now_datetime(), minutes=-10), "expires_at": add_to_date(now_datetime(), minutes=5)},
			update_modified=False,
		)
		frappe.db.commit()
		for name in ("get_customer_order", "get_order_status"):
			status, body = self.get(name, session=session)
			self.assertEqual(status, 200, body)
		# the profile's idle minutes (default 30) from now, not the 5 minutes that were left
		self.assertGreater(self.expires_at(), add_to_date(now_datetime(), minutes=20))


class TestTheKitchenSeesWhoServesTheGuests(SelfOrderingCase):
	"""The kitchen screen writes the name of the person next to the table, and the guests' order is served by
	the staff who opened the table, not by the administrator the server runs the guests' calls as."""

	def _full_name(self, user):
		return frappe.db.get_value("User", user, "full_name")

	def _kot_users(self, invoice):
		return set(frappe.get_all("URY KOT", filters={"invoice": invoice}, pluck="user"))

	def test_the_ticket_of_the_guests_order_has_the_name_of_the_staff_who_opened_the_table(self):
		for opener in (CASHIER, CAPTAIN):
			self.staff_close()
			self.staff_open(user=opener)
			session = self.scan()
			invoice = self.order(session)["invoice"]
			self.assertEqual(frappe.db.get_value("POS Invoice", invoice, "waiter"), opener)
			self.assertEqual(self._kot_users(invoice), {self._full_name(opener)})
			self.assertNotIn("Administrator", self._kot_users(invoice))
			frappe.db.set_value("POS Invoice", invoice, "docstatus", 2)  # over; the next opener starts fresh
			frappe.db.commit()

	def test_what_the_guests_add_later_carries_the_same_name(self):
		self.staff_open(user=CASHIER)
		session = self.scan()
		invoice = self.order(session)["invoice"]
		self.order(session)
		self.assertEqual(self._kot_users(invoice), {self._full_name(CASHIER)})
		self.assertEqual(frappe.db.count("URY KOT", {"invoice": invoice}), 2)

	def test_the_ticket_of_a_staff_order_keeps_the_name_of_who_sent_it(self):
		invoice = place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLE)
		self.assertEqual(self._kot_users(invoice), {self._full_name(CAPTAIN)})


class TestItemNotes(SelfOrderingCase):
	def test_with_notes_switched_off_the_note_is_dropped(self):
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, "enable_item_notes", 0)
		frappe.db.commit()
		self.staff_open()
		session = self.scan()
		invoice = add_customer_items(session, [{"item": FOOD_ITEM, "qty": 1, "comment": "わさび抜き"}])["invoice"]
		self.assertEqual(frappe.db.get_value("POS Invoice Item", {"parent": invoice}, "comment") or "", "")
		self.assertEqual(tickets_since(invoice, set())["New Order"], [(FOOD_ITEM, 1, "", 0)])

	def test_with_notes_on_the_note_is_kept_and_cut_to_140_characters(self):
		self.staff_open()
		session = self.scan()
		invoice = add_customer_items(session, [{"item": FOOD_ITEM, "qty": 1, "comment": "あ" * 300}])["invoice"]
		self.assertEqual(len(frappe.db.get_value("POS Invoice Item", {"parent": invoice}, "comment")), 140)


class TestWhichTablesTheButtonIsNotOfferedFor(SelfOrderingCase):
	"""A table is held by a printed bill only if it is occupied and nothing but printed bills are on it.
	Printing releases the table, so this does not arise by itself (a guard, in case it does)."""

	def tables(self):
		with as_user(CASHIER):
			return self_ordering.get_open_tables()

	def test_a_table_with_a_printed_bill_that_is_free_again_is_not_blocked(self):
		invoice = place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLE)
		print_bill(invoice, CASHIER)
		self.assertNotIn(TABLE, self.tables()["blocked"])

	def test_a_table_that_is_occupied_by_nothing_but_a_printed_bill_is_blocked_and_refused(self):
		invoice = place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLE)
		print_bill(invoice, CASHIER)
		frappe.db.set_value("URY Table", TABLE, "occupied", 1)  # the state that printing does not leave
		frappe.db.commit()
		self.assertIn(TABLE, self.tables()["blocked"])
		self.assertNotIn(OTHER_TABLE, self.tables()["blocked"])
		self.refused("Order closed", self.staff_open)
		self.assertFalse(table_row()["self_order_open"])

	def test_the_next_guests_order_on_the_table_does_not_block_it(self):
		old = place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLE)
		print_bill(old, CASHIER)
		place_order(CAPTAIN, [(ALCOHOL_ITEM, 1)], table=TABLE)  # a new order: the table is occupied again
		self.assertEqual(frappe.db.get_value("URY Table", TABLE, "occupied"), 1)
		self.assertNotIn(TABLE, self.tables()["blocked"])
		self.assertTrue(self.staff_open()["tables"])


def items_of(invoice):
	return [
		(row.item_code, int(row.qty), row.comment or "")
		for row in frappe.get_all(
			"POS Invoice Item", filters={"parent": invoice}, fields=["item_code", "qty", "comment"], order_by="idx"
		)
	]


class TestTheNextGuestsWhileTheLastBillIsUnpaid(SelfOrderingCase):
	"""The last guests have the bill and are at the cash desk; the staff seat the next guests at once. The
	table opens again, and the new guests' dishes go on a new order, never on the one that is printed."""

	def setUp(self):
		super().setUp()
		self.old = place_order(CAPTAIN, [(FOOD_ITEM, 2)], table=TABLE)
		print_bill(self.old, CASHIER)
		self.old_before = frappe.db.get_value(
			"POS Invoice", self.old, ["grand_total", "rounded_total", "invoice_printed", "docstatus"]
		)
		self.old_items = items_of(self.old)

	def _old_is_untouched(self):
		self.assertEqual(
			frappe.db.get_value("POS Invoice", self.old, ["grand_total", "rounded_total", "invoice_printed", "docstatus"]),
			self.old_before,
		)
		self.assertEqual(items_of(self.old), self.old_items)

	def test_the_new_guests_get_a_new_order_and_the_printed_one_stays_as_it_was(self):
		self.staff_open()
		session = self.scan()
		new = add_customer_items(session, [{"item": ALCOHOL_ITEM, "qty": 1, "comment": "冷えたもの"}], age_confirmed=1)["invoice"]
		self.assertNotEqual(new, self.old)
		self.assertEqual(frappe.db.get_value("POS Invoice", new, "invoice_printed"), 0)
		self.assertEqual(items_of(new), [(ALCOHOL_ITEM, 1, "冷えたもの")])
		self._old_is_untouched()
		self.assertEqual(frappe.db.get_value("URY Table", TABLE, "occupied"), 1)

	def test_what_they_add_later_goes_to_the_new_order_and_so_do_other_phones_at_the_table(self):
		self.staff_open()
		first, second = self.scan(), self.scan()
		new = add_customer_items(first, [{"item": FOOD_ITEM, "qty": 1}])["invoice"]
		self.assertEqual(add_customer_items(first, [{"item": FOOD_ITEM, "qty": 1}])["invoice"], new)
		self.assertEqual(add_customer_items(second, [{"item": FOOD_ITEM, "qty": 1}])["invoice"], new)
		self.assertEqual(len(items_of(new)), 3)
		self._old_is_untouched()

	def test_the_guests_see_only_their_own_order(self):
		self.staff_open()
		session = self.scan()
		order = add_customer_items(session, [{"item": FOOD_ITEM, "qty": 1}])
		self.assertEqual([row["qty"] for row in order["items"]], [1])
		self.assertEqual(order["grand_total"], 1100)  # not 3300: the printed bill is not theirs

	def test_each_order_is_paid_on_its_own_and_the_table_is_released_when_both_are_done(self):
		self.staff_open()
		session = self.scan()
		new = add_customer_items(session, [{"item": FOOD_ITEM, "qty": 1}])["invoice"]

		pay_order(self.old, CASHIER)  # the last guests pay at the desk
		self.assertEqual(frappe.db.get_value("POS Invoice", self.old, "docstatus"), 1)
		self.assertEqual(frappe.db.get_value("URY Table", TABLE, "occupied"), 1)  # the new guests are there
		self.assertTrue(table_row()["self_order_open"])  # they may still order
		self.assertEqual(self.order(session)["invoice"], new)

		print_bill(new, CASHIER)
		self.assertEqual(frappe.db.get_value("URY Table", TABLE, "occupied"), 0)
		self.assertFalse(table_row()["self_order_open"])
		pay_order(new, CASHIER)
		self.assertEqual(frappe.db.get_value("POS Invoice", new, "docstatus"), 1)
		self.assertEqual(frappe.db.get_value("URY Table", TABLE, "occupied"), 0)

	def test_the_shift_cannot_be_closed_before_both_are_dealt_with(self):
		self.staff_open()
		new = add_customer_items(self.scan(), [{"item": FOOD_ITEM, "qty": 1}])["invoice"]

		with self.assertRaises(frappe.ValidationError) as both:
			close_shift(self.opening)
		self.assertIn(self.old, str(both.exception))
		self.assertIn(new, str(both.exception))

		pay_order(self.old, CASHIER)
		with self.assertRaises(frappe.ValidationError) as one:
			close_shift(self.opening)
		self.assertNotIn(self.old, str(one.exception))
		self.assertIn(new, str(one.exception))

		print_bill(new, CASHIER)
		pay_order(new, CASHIER)
		close_shift(self.opening)  # now it can be closed
		self.assertFalse(branch_is_open(BRANCH))


class TestWhichOrderTheFirstDishGoesTo(SelfOrderingCase):
	"""A guest who scans after a bill was split finds two open orders on the table: the dishes go on the
	original, the same one every time; the part that was split off does not get the guests' dishes."""

	def setUp(self):
		super().setUp()
		from ury.ury.doctype.ury_order.ury_order import split_bill

		self.source = place_order(CAPTAIN, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)], table=TABLE)
		row = frappe.get_all("POS Invoice Item", filters={"parent": self.source, "item_code": ALCOHOL_ITEM}, pluck="name")[0]
		with as_user(CASHIER):
			self.sibling = split_bill(self.source, [{"name": row, "qty": 1}])["new_invoice"]
		frappe.db.commit()
		self.sibling_items = items_of(self.sibling)

	def test_it_goes_to_the_original_every_time(self):
		self.staff_open()
		for _ in range(3):
			order = add_customer_items(self.scan(), [{"item": FOOD_ITEM, "qty": 1}])
			self.assertEqual(order["invoice"], self.source)
		self.assertEqual(items_of(self.sibling), self.sibling_items)

	def test_the_split_off_order_is_not_the_one_the_guests_see(self):
		self.staff_open()
		session = self.scan()
		order = add_customer_items(session, [{"item": FOOD_ITEM, "qty": 1}])
		self.assertEqual(order["invoice"], self.source)
		self.assertEqual(frappe.db.get_value("POS Invoice", self.sibling, "custom_ordering_session"), None)


class TestTheOrderTheGuestsSeeIsTheOneTheyOrderOn(SelfOrderingCase):
	"""A phone that has not ordered yet is shown the order of the table its dishes would go on (the same
	rule as when it orders), so the order and the total with the cart agree; never an order that is printed."""

	def _ordered_total(self, session):
		return preview_customer_cart(session, [])["ordered_total"]

	def test_a_phone_that_has_not_ordered_sees_the_order_another_phone_started(self):
		self.staff_open()
		first, second = self.scan(), self.scan()
		order = add_customer_items(first, [{"item": FOOD_ITEM, "qty": 2}])
		seen = get_customer_order(second)
		self.assertEqual(seen["state"], "open")
		self.assertEqual(seen["invoice"], order["invoice"])
		self.assertEqual([row["qty"] for row in seen["items"]], [2])
		self.assertEqual(seen["grand_total"], self._ordered_total(second))

	def test_the_order_of_the_waiter_is_seen_before_anything_is_ordered(self):
		order = place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLE)
		self.staff_open()
		session = self.scan()
		seen = get_customer_order(session)
		self.assertEqual(seen["invoice"], order)
		self.assertEqual(seen["grand_total"], self._ordered_total(session))
		self.assertGreater(seen["grand_total"], 0)

	def test_nothing_is_shown_when_the_table_has_no_order(self):
		self.staff_open()
		self.assertEqual(get_customer_order(self.scan())["state"], "none")

	def test_the_printed_order_of_the_last_guests_is_not_shown_to_the_new_guests(self):
		old = place_order(CAPTAIN, [(FOOD_ITEM, 2)], table=TABLE)
		print_bill(old, CASHIER)
		self.staff_open()
		seen = get_customer_order(self.scan())
		self.assertEqual(seen["state"], "none")
		self.assertEqual(seen["items"], [])

	def test_only_the_order_of_the_new_guests_is_shown_while_the_old_one_is_printed(self):
		old = place_order(CAPTAIN, [(FOOD_ITEM, 2)], table=TABLE)
		print_bill(old, CASHIER)
		self.staff_open()
		first, second = self.scan(), self.scan()
		new = add_customer_items(first, [{"item": FOOD_ITEM, "qty": 1}])["invoice"]
		seen = get_customer_order(second)
		self.assertEqual(seen["invoice"], new)
		self.assertEqual(seen["grand_total"], 1100)


class TestPayingAndAskingForTheBillAreOffUntilTheStaffSideIsThere(SelfOrderingCase):
	"""「お会計をお願いする」 and 「オンラインで支払う」 do nothing the staff could see until the POS shows the
	calls (batch 4). A profile has both off unless someone turns them on, the page is told so and the server
	refuses the calls."""

	def test_both_are_off_by_default_in_the_doctype(self):
		import json
		from pathlib import Path

		path = Path(frappe.get_app_path("ury")) / "ury/doctype/ury_self_ordering_profile/ury_self_ordering_profile.json"
		fields = {f["fieldname"]: f for f in json.loads(path.read_text())["fields"]}
		for name in ("enable_request_bill", "enable_customer_payment", "enable_payment_link"):
			self.assertEqual(str(fields[name].get("default", "0")), "0", name)

	def test_the_page_is_told_that_neither_is_offered(self):
		self.staff_open()
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, {"enable_request_bill": 0, "enable_customer_payment": 0})
		token = generate_qr_token(PROFILE, TABLE)
		capabilities = get_ordering_context(token=token)["capabilities"]
		self.assertFalse(capabilities["request_bill_enabled"])
		self.assertFalse(capabilities["customer_payment_enabled"])

	def test_the_server_refuses_both_calls(self):
		from ury.ury.api.self_ordering import create_payment_request, request_bill

		self.staff_open()
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, {"enable_request_bill": 0, "enable_customer_payment": 0})
		session = self.scan()
		add_customer_items(session, [{"item": FOOD_ITEM, "qty": 1}])
		with self.assertRaises(frappe.ValidationError):
			request_bill(session)
		with self.assertRaises(frappe.ValidationError):
			create_payment_request(session)


class TestAskingForTheBillTellsTheStaff(SelfOrderingCase):
	def test_the_staff_of_the_branch_are_told_after_the_commit_and_asking_twice_tells_nobody_again(self):
		from ury.ury.api.self_ordering import request_bill

		self.staff_open()
		original = frappe.db.get_value("URY Self Ordering Profile", PROFILE, "enable_request_bill")
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, "enable_request_bill", 1)
		frappe.db.commit()
		self.addCleanup(lambda: (frappe.db.set_value("URY Self Ordering Profile", PROFILE, "enable_request_bill", original), frappe.db.commit()))
		session = self.scan()
		add_customer_items(session, [{"item": FOOD_ITEM, "qty": 1}])
		with mock.patch("ury.ury.api.service_requests.publish_to_branch") as publish:
			first = request_bill(session)
			second = request_bill(session)
		self.assertEqual(first["status"], "Requested")
		self.assertEqual(second["status"], "Already Requested")
		self.assertEqual(publish.call_count, 1)
		self.assertEqual(publish.call_args.args[1]["kind"], "new")
		self.assertEqual(publish.call_args.args[1]["table"], TABLE)
		self.assertTrue(publish.call_args.kwargs.get("after_commit"))


class TestTheStaffAreToldWhenGuestsOrderAtATable(SelfOrderingCase):
	"""The register's table list is loaded once; the table is occupied in the database as soon as the guests order, so the
	POS has to be told (found in the browser test: a table called for the bill while the card still said 空席)."""

	def test_the_staff_of_the_branch_are_told_the_table_is_occupied_after_the_commit(self):
		self.staff_open()
		session = self.scan()
		with mock.patch("ury.ury.api.self_ordering.publish_to_branch") as publish:
			add_customer_items(session, [{"item": FOOD_ITEM, "qty": 1}])
		calls = [c for c in publish.call_args_list if c.args[0] == "table_updated"]
		self.assertEqual(len(calls), 1)
		self.assertEqual(calls[0].args[1]["table"], TABLE)
		self.assertEqual(calls[0].args[1]["kind"], "ordered")
		self.assertTrue(calls[0].kwargs.get("after_commit"))
		self.assertEqual(frappe.db.get_value("URY Table", TABLE, "occupied"), 1)


class TestTheOrderTellsThatTheBillWasAskedFor(SelfOrderingCase):
	"""After a reload the page must still say 「お会計をお呼びしました」, so the order the page reads says it."""

	def setUp(self):
		super().setUp()
		self.staff_open()
		original = frappe.db.get_value("URY Self Ordering Profile", PROFILE, "enable_request_bill")
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, "enable_request_bill", 1)
		frappe.db.commit()
		self.addCleanup(lambda: (frappe.db.set_value("URY Self Ordering Profile", PROFILE, "enable_request_bill", original), frappe.db.commit()))
		self.session = self.scan()
		add_customer_items(self.session, [{"item": FOOD_ITEM, "qty": 1}])

	def test_not_asked_before_the_button_and_asked_after_it(self):
		from ury.ury.api.self_ordering import get_customer_order, request_bill

		self.assertFalse(get_customer_order(self.session)["bill_requested"])
		request_bill(self.session)
		self.assertTrue(get_customer_order(self.session)["bill_requested"])

	def test_a_resolved_request_is_not_asked_any_more(self):
		from ury.ury.api.self_ordering import get_customer_order, request_bill

		request_bill(self.session)
		frappe.db.set_value("URY Service Request", {"session": self.session_name()}, "status", "Resolved")
		self.assertFalse(get_customer_order(self.session)["bill_requested"])

	def test_an_order_that_was_not_started_says_not_asked(self):
		from ury.ury.api.self_ordering import get_customer_order

		fresh = self.scan()
		self.assertFalse(get_customer_order(fresh)["bill_requested"])

	def session_name(self):
		return frappe.db.get_value("URY Service Request", {"invoice": ["is", "set"]}, "session")


class TestThePricesTheGuestsSeeIncludeTax(SelfOrderingCase):
	"""総額表示: the guests are shown prices with the tax, calculated by the server, and the total of the
	cart and of the order is the amount the bill will have. The tax-exclusive price is not sent at all."""

	def pickup_session(self):
		profile = frappe.get_doc("URY Self Ordering Profile", PROFILE)
		raw, _session = self_ordering._open_session(profile, "QR Pickup", None)
		return raw

	def cart(self, session, items):
		return self_ordering.preview_customer_cart(session, items)

	def prices(self, session):
		menu = get_customer_menu(session)
		return {row["item"]: row for row in menu["items"]}

	def test_a_dine_in_menu_shows_the_price_with_ten_percent(self):
		self.staff_open()
		prices = self.prices(self.scan())
		self.assertEqual(prices[FOOD_ITEM]["price_incl_tax"], 1100)
		self.assertEqual(prices[ALCOHOL_ITEM]["price_incl_tax"], 550)

	def test_a_take_away_menu_shows_eight_percent_for_the_food(self):
		prices = self.prices(self.pickup_session())
		self.assertEqual(prices[FOOD_ITEM]["price_incl_tax"], 1080)
		self.assertEqual(prices[ALCOHOL_ITEM]["price_incl_tax"], 550)

	def test_the_price_without_tax_is_not_sent(self):
		self.staff_open()
		for row in get_customer_menu(self.scan())["items"]:
			self.assertNotIn("rate", row)

	def test_the_tail_of_the_tax_is_rounded_the_way_the_bill_does(self):
		original = frappe.db.get_value("Item Price", {"item_code": FOOD_ITEM, "selling": 1}, "price_list_rate")
		frappe.db.sql("update `tabItem Price` set price_list_rate = 333 where item_code = %s and selling = 1", FOOD_ITEM)
		frappe.db.commit()
		self.addCleanup(self._restore_price, original)
		# 333 x 8% = 26.64: the bill cuts it to 26
		self.assertEqual(self.prices(self.pickup_session())[FOOD_ITEM]["price_incl_tax"], 359)

	def _restore_price(self, original):
		frappe.db.sql("update `tabItem Price` set price_list_rate = %s where item_code = %s and selling = 1", (original, FOOD_ITEM))
		frappe.db.commit()

	def test_the_cart_total_is_with_tax(self):
		self.staff_open()
		total = self.cart(self.scan(), [{"item": FOOD_ITEM, "qty": 1}, {"item": ALCOHOL_ITEM, "qty": 2}])
		self.assertEqual(total["rounded_total"], 2200)
		self.assertEqual([(t["rate"], t["tax_amount"]) for t in total["taxes"]], [(10, 200)])
		self.assertEqual(total["ordered_total"], 0)

	def test_an_empty_cart_is_zero(self):
		self.staff_open()
		self.assertEqual(self.cart(self.scan(), [])["rounded_total"], 0)

	def test_the_cart_total_is_what_the_order_will_have(self):
		self.staff_open()
		session = self.scan()
		items = [{"item": FOOD_ITEM, "qty": 3}, {"item": ALCOHOL_ITEM, "qty": 1}]
		shown = self.cart(session, items)["rounded_total"]
		order = add_customer_items(session, items, age_confirmed=1)
		self.assertEqual(order["grand_total"], shown)
		self.assertEqual(frappe.db.get_value("POS Invoice", order["invoice"], "rounded_total"), shown)

	def test_what_was_ordered_is_part_of_the_total(self):
		self.staff_open()
		session = self.scan()
		self.order(session)  # 1100
		total = self.cart(session, [{"item": ALCOHOL_ITEM, "qty": 2}])
		self.assertEqual(total["ordered_total"], 1100)
		self.assertEqual(total["rounded_total"], 2200)  # the order and the cart together

	def test_the_cart_total_of_a_take_away_order(self):
		total = self.cart(self.pickup_session(), [{"item": FOOD_ITEM, "qty": 1}, {"item": ALCOHOL_ITEM, "qty": 1}])
		self.assertEqual(total["rounded_total"], 1630)
		self.assertEqual([(t["rate"], t["tax_amount"]) for t in total["taxes"]], [(10, 50), (8, 80)])

	def test_the_cart_only_takes_what_the_menu_has(self):
		self.staff_open()
		self.refused("Item not available", self.cart, self.scan(), [{"item": "no such dish", "qty": 1}])

	def test_the_cart_needs_a_valid_session(self):
		with self.assertRaises((frappe.ValidationError, frappe.PermissionError)):
			self.cart("not-a-session", [{"item": FOOD_ITEM, "qty": 1}])

	def test_the_order_shows_each_line_with_tax(self):
		self.staff_open()
		session = self.scan()
		order = self.order(session, quantity=2)
		line = order["items"][0]
		self.assertEqual((line["price_incl_tax"], line["amount_incl_tax"]), (1100, 2200))
		for key in ("rate", "amount"):
			self.assertNotIn(key, line)
		self.assertEqual(order["grand_total"], 2200)


class TestWhichDishesTheGuestsMayOrder(SelfOrderingCase):
	"""「セルフオーダー可」: a dish that is not ticked is not offered, and cannot be ordered by calling the
	server directly either."""

	def _row(self, item=FOOD_ITEM):
		return frappe.get_all("URY Menu Item", filters={"item": item}, pluck="name")[0]

	def _untick(self, item=FOOD_ITEM):
		row = self._row(item)
		frappe.db.set_value("URY Menu Item", row, "self_order_allowed", 0)
		frappe.db.commit()
		self.addCleanup(self._tick, row)

	def _tick(self, row):
		frappe.db.set_value("URY Menu Item", row, "self_order_allowed", 1)
		frappe.db.commit()

	def test_every_dish_that_was_on_the_menu_before_is_allowed(self):
		# the column is new: the rows that were there get its default, so no patch is needed
		self.assertTrue(frappe.db.count("URY Menu Item"))
		self.assertEqual(frappe.db.count("URY Menu Item", {"self_order_allowed": ["!=", 1]}), 0)

	def test_a_new_dish_is_allowed_unless_it_is_unticked(self):
		self.assertEqual(frappe.get_meta("URY Menu Item").get_field("self_order_allowed").default, "1")

	def test_an_unticked_dish_is_not_on_the_menu(self):
		self._untick()
		self.staff_open()
		items = [row["item"] for row in get_customer_menu(self.scan())["items"]]
		self.assertNotIn(FOOD_ITEM, items)
		self.assertIn(ALCOHOL_ITEM, items)

	def test_an_unticked_dish_cannot_be_ordered(self):
		self._untick()
		self.staff_open()
		session = self.scan()
		self.refused("Item not available", add_customer_items, session, [{"item": FOOD_ITEM, "qty": 1}])
		self.assertIsNone(frappe.db.get_value("URY Ordering Session", {"ordering_profile": PROFILE}, "invoice"))

	def test_an_unticked_dish_is_not_priced_or_shown(self):
		self._untick()
		self.staff_open()
		session = self.scan()
		self.refused("Item not available", self_ordering.preview_customer_cart, session, [{"item": FOOD_ITEM, "qty": 1}])
		with self.assertRaises(frappe.DoesNotExistError):
			self_ordering.get_customer_product(session, FOOD_ITEM)

	def test_the_staff_still_have_the_dish(self):
		self._untick()
		self.assertTrue(place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLE))


class TestAgeConfirmation(SelfOrderingCase):
	"""Alcohol (the item group the setup wizard makes, and the groups below it) asks "20歳以上ですか？" the first
	time in a session. The server records the answer "yes" on the session and does not take alcohol from a
	session that has no such record. A new session (the table opened again, a new scan) asks again."""

	ALCOHOL = [{"item": ALCOHOL_ITEM, "qty": 1}]

	def _groups(self):
		return frappe.get_all("URY Age Check Item Group", filters={"parent": PROFILE}, pluck="item_group")

	def _set_groups(self, groups):
		profile = frappe.get_doc("URY Self Ordering Profile", PROFILE)
		profile.set("age_check_item_groups", [{"item_group": group} for group in groups])
		profile.save(ignore_permissions=True)
		frappe.db.commit()

	def _recorded(self, raw_session):
		import hashlib

		token_hash = hashlib.sha256(raw_session.encode()).hexdigest()
		return frappe.db.get_value("URY Ordering Session", {"token_hash": token_hash}, "age_confirmed")

	def menu(self):
		self.staff_open()
		return {row["item"]: row for row in get_customer_menu(self.scan())["items"]}

	def test_a_new_profile_asks_for_the_alcohol_group_of_the_wizard(self):
		from ury.setup.jp_tax import ALCOHOL_GROUP

		self.assertEqual(self._groups(), [ALCOHOL_GROUP])

	def test_the_dishes_in_the_groups_below_alcohol_are_asked_about_too(self):
		from ury.setup.jp_tax import ALCOHOL_GROUP

		# the test beer is in "Bar", a group below the alcohol group
		self.assertEqual(frappe.db.get_value("Item Group", frappe.db.get_value("Item", ALCOHOL_ITEM, "item_group"), "parent_item_group"), ALCOHOL_GROUP)
		menu = self.menu()
		self.assertTrue(menu[ALCOHOL_ITEM]["age_check"])
		self.assertFalse(menu[FOOD_ITEM]["age_check"])

	def test_a_profile_without_the_group_asks_about_nothing(self):
		self._set_groups([])
		self.assertFalse(self.menu()[ALCOHOL_ITEM]["age_check"])
		session = self.scan()
		self.assertTrue(add_customer_items(session, self.ALCOHOL)["invoice"])

	def test_alcohol_from_a_session_without_the_answer_is_refused_and_nothing_is_saved(self):
		self.staff_open()
		session = self.scan()
		self.refused("Age confirmation required", add_customer_items, session, self.ALCOHOL)
		self.refused("Age confirmation required", add_customer_items, session, self.ALCOHOL, age_confirmed=0)
		self.refused("Age confirmation required", add_customer_items, session, self.ALCOHOL, age_confirmed="0")
		self.assertEqual(frappe.db.count("POS Invoice", {"docstatus": 0, "restaurant_table": TABLE}), 0)
		self.assertFalse(self._recorded(session))

	def test_the_answer_yes_is_recorded_on_the_session(self):
		self.staff_open()
		session = self.scan()
		self.assertFalse(get_customer_menu(session)["age_confirmed"])
		order = add_customer_items(session, self.ALCOHOL, age_confirmed=1)
		self.assertEqual([row["item_code"] for row in order["items"]], [ALCOHOL_ITEM])
		self.assertTrue(self._recorded(session))
		self.assertTrue(get_customer_menu(session)["age_confirmed"])  # the page knows after a reload

	def test_the_answer_is_not_asked_again_in_the_same_session(self):
		self.staff_open()
		session = self.scan()
		add_customer_items(session, self.ALCOHOL, age_confirmed="1")  # the browser sends text
		more = add_customer_items(session, self.ALCOHOL)  # no answer sent: the session has it
		self.assertEqual(len(more["items"]), 2)

	def test_a_new_session_asks_again(self):
		self.staff_open()
		first = self.scan()
		add_customer_items(first, self.ALCOHOL, age_confirmed=1)
		second = self.scan()  # the next scan of the code is a new session
		self.assertNotEqual(first, second)
		self.assertFalse(get_customer_menu(second)["age_confirmed"])
		self.refused("Age confirmation required", add_customer_items, second, self.ALCOHOL)

	def test_after_the_table_is_opened_again_the_new_guests_are_asked(self):
		self.staff_open()
		old = self.scan()
		add_customer_items(old, self.ALCOHOL, age_confirmed=1)
		self.staff_close()
		self.staff_open()
		new = self.scan()
		self.refused("Age confirmation required", add_customer_items, new, self.ALCOHOL)
		# and the old session is no longer valid at all
		self.refused("Table closed", add_customer_items, old, self.ALCOHOL)

	def test_food_needs_no_answer_and_records_nothing(self):
		self.staff_open()
		session = self.scan()
		self.assertTrue(self.order(session)["invoice"])
		self.assertFalse(self._recorded(session))

	def test_a_request_with_a_dish_that_asks_the_age_needs_the_answer_even_with_food(self):
		self.staff_open()
		self.refused(
			"Age confirmation required",
			add_customer_items, self.scan(), [{"item": FOOD_ITEM, "qty": 1}, {"item": ALCOHOL_ITEM, "qty": 1}],
		)

	def test_the_answer_no_is_not_recorded_and_the_next_alcohol_asks_again(self):
		# "いいえ" sends nothing to the server: the dish is not put in the cart
		self.staff_open()
		session = self.scan()
		self.refused("Age confirmation required", add_customer_items, session, self.ALCOHOL, age_confirmed=0)
		self.assertFalse(self._recorded(session))
		self.refused("Age confirmation required", add_customer_items, session, self.ALCOHOL)
		self.assertTrue(add_customer_items(session, self.ALCOHOL, age_confirmed=1)["invoice"])

	def test_the_cart_total_does_not_ask(self):
		self.staff_open()
		self.assertTrue(self_ordering.preview_customer_cart(self.scan(), self.ALCOHOL)["rounded_total"])


class TestTheReasonsAGuestIsRefusedHaveATitle(SelfOrderingCase):
	"""The ordering page shows its own text for each reason, by the `title` of the error: all the ways a
	guest's call can be refused because the ordering is over have one."""

	CALLS = (
		("get_customer_menu", lambda session: get_customer_menu(session)),
		("preview_customer_cart", lambda session: self_ordering.preview_customer_cart(session, [{"item": FOOD_ITEM, "qty": 1}])),
		("add_customer_items", lambda session: add_customer_items(session, [{"item": FOOD_ITEM, "qty": 1}])),
		("confirm_age", lambda session: self_ordering.confirm_age(session)),
	)

	def test_a_session_of_a_table_that_was_opened_again_is_refused_as_table_closed(self):
		self.staff_open()
		old = self.scan()
		self.staff_close()
		self.staff_open()
		for name, call in self.CALLS:
			with self.subTest(name):
				self.refused("Table closed", call, old)

	def test_a_table_that_was_closed_is_refused_as_table_closed(self):
		self.staff_open()
		session = self.scan()
		self.staff_close()
		for name, call in self.CALLS:
			with self.subTest(name):
				self.refused("Table closed", call, session)

	def test_a_shift_that_was_closed_is_refused_as_store_closed(self):
		self.staff_open()
		session = self.scan()
		close_shift(self.opening)
		for name, call in self.CALLS:
			with self.subTest(name):
				self.refused("Store closed", call, session)

	def test_a_session_that_is_not_valid_is_refused_as_session_expired(self):
		for name, call in self.CALLS:
			with self.subTest(name):
				self.refused("Session expired", call, "not-a-session")
		self.refused("Session expired", get_customer_menu, "")

	def test_a_session_that_ran_out_is_refused_as_session_expired(self):
		self.staff_open()
		session = self.scan()
		frappe.db.set_value("URY Ordering Session", {"ordering_profile": PROFILE}, "expires_at", add_to_date(now_datetime(), minutes=-5))
		frappe.db.commit()
		self.refused("Session expired", get_customer_menu, session)

	def test_an_order_that_is_over_is_refused_as_order_closed(self):
		self.staff_open()
		session = self.scan()
		invoice = self.order(session)["invoice"]
		print_bill(invoice)
		self.staff_open()  # the table is opened again; the old session is made to belong to that opening
		old = session
		frappe.db.set_value("URY Ordering Session", {"ordering_profile": PROFILE, "invoice": invoice}, "table_opening", frappe.db.get_value("URY Table", TABLE, "self_order_opening"))
		frappe.db.commit()
		self.refused("Order closed", add_customer_items, old, [{"item": FOOD_ITEM, "qty": 1}])


class TestRequestsThatOverlap(SelfOrderingCase):
	"""A page sends several requests at once (a reload asks for the menu, the order and the total), and the session
	is the same in all of them. Saving the session in each of them made the later ones fail with
	TimestampMismatchError ("Document has been modified after you have opened it"). The calls that only read do
	not save the session; an order that meets another save of its invoice is tried once more."""

	def _name(self, raw):
		import hashlib

		return frappe.db.get_value("URY Ordering Session", {"token_hash": hashlib.sha256(raw.encode()).hexdigest()}, "name")

	def _long_idle(self, name):
		frappe.db.set_value(
			"URY Ordering Session", name, "last_activity", add_to_date(now_datetime(), minutes=-5), update_modified=False
		)
		frappe.db.commit()

	def _touch_session_once(self, name, calls):
		"""A stand-in for another request saving the session between our read and our write."""

		def touch():
			if not calls:
				calls.append(1)
				frappe.db.set_value("URY Ordering Session", name, "status", "Active")  # changes `modified`

		return touch

	def test_a_request_is_not_refused_when_another_one_saved_the_session_meanwhile(self):
		from unittest.mock import patch

		self.staff_open()
		raw = self.scan()
		name = self._name(raw)
		self._long_idle(name)  # so that this request is the one that writes the session
		calls = []
		touch = self._touch_session_once(name, calls)
		real = self_ordering.add_to_date

		def other_request_saves_first(*args, **kwargs):
			touch()
			return real(*args, **kwargs)

		with patch.object(self_ordering, "add_to_date", other_request_saves_first):
			menu = get_customer_menu(raw)
		self.assertTrue(menu["items"])
		self.assertEqual(calls, [1])  # the other save did happen in between

	def test_the_calls_that_only_read_do_not_write_the_session(self):
		self.staff_open()
		raw = self.scan()
		name = self._name(raw)
		fields = ["modified", "last_activity", "expires_at"]
		before = frappe.db.get_value("URY Ordering Session", name, fields)
		get_customer_menu(raw)
		get_customer_order(raw)
		get_order_status(raw)
		self_ordering.preview_customer_cart(raw, [{"item": FOOD_ITEM, "qty": 1}])
		self.assertEqual(frappe.db.get_value("URY Ordering Session", name, fields), before)

	def test_a_session_that_has_been_idle_for_a_while_is_kept_alive_by_a_request(self):
		self.staff_open()
		raw = self.scan()
		name = self._name(raw)
		self._long_idle(name)
		old = frappe.db.get_value("URY Ordering Session", name, "last_activity")
		get_customer_menu(raw)
		self.assertGreater(frappe.db.get_value("URY Ordering Session", name, "last_activity"), old)

	def test_the_first_order_of_a_session_is_not_refused_when_the_session_was_saved_meanwhile(self):
		from unittest.mock import patch

		self.staff_open()
		raw = self.scan()
		name = self._name(raw)
		calls = []
		touch = self._touch_session_once(name, calls)
		real = self_ordering._invoice_to_add_to

		def other_request_saves_first(table):
			touch()
			return real(table)

		with patch.object(self_ordering, "_invoice_to_add_to", other_request_saves_first):
			order = add_customer_items(raw, [{"item": FOOD_ITEM, "qty": 1}])
		self.assertEqual(calls, [1])
		self.assertEqual(frappe.db.get_value("URY Ordering Session", name, "invoice"), order["invoice"])

	def _first_order_then(self):
		self.staff_open()
		raw = self.scan()
		invoice = self.order(raw)["invoice"]
		frappe.db.commit()  # every request of a guest is a transaction of its own: the first order is saved
		return raw, invoice

	def _rows(self, invoice):
		return frappe.db.count("POS Invoice Item", {"parent": invoice})

	def _kots(self, invoice):
		return frappe.db.count("URY KOT", {"invoice": invoice})

	def _touch_invoice(self, invoice, times):
		"""Another save of the invoice after we loaded it, the first `times` times it is loaded."""
		real = self_ordering._resolve_or_create_pos_invoice
		counter = {"n": 0}

		def resolve(*args, **kwargs):
			result = real(*args, **kwargs)
			if result[1] and counter["n"] < times:
				counter["n"] += 1
				frappe.db.set_value("POS Invoice", result[1], "remarks", f"saved by someone else {counter['n']}")
			return result

		return resolve, counter

	def test_an_order_that_meets_another_save_of_its_invoice_is_tried_once_more(self):
		from unittest.mock import patch

		raw, invoice = self._first_order_then()
		resolve, counter = self._touch_invoice(invoice, times=1)
		with patch.object(self_ordering, "_resolve_or_create_pos_invoice", resolve):
			order = add_customer_items(raw, [{"item": FOOD_ITEM, "qty": 1}])
		self.assertEqual(counter["n"], 1)  # it did meet the other save
		self.assertEqual(order["invoice"], invoice)
		self.assertEqual(self._rows(invoice), 2)  # the dish is on the order once, not twice
		self.assertEqual(self._kots(invoice), 2)  # and the kitchen got one ticket for it

	def test_an_order_that_keeps_meeting_other_saves_asks_the_guest_to_try_again_and_changes_nothing(self):
		from unittest.mock import patch

		raw, invoice = self._first_order_then()
		resolve, counter = self._touch_invoice(invoice, times=99)
		with patch.object(self_ordering, "_resolve_or_create_pos_invoice", resolve):
			self.refused("Try again", add_customer_items, raw, [{"item": FOOD_ITEM, "qty": 1}])
		self.assertEqual(counter["n"], 2)  # the first try and the one more
		self.assertEqual(self._rows(invoice), 1)
		self.assertEqual(self._kots(invoice), 1)

	def test_the_answer_to_the_age_question_survives_the_second_try(self):
		from unittest.mock import patch

		self.staff_open()
		raw = self.scan()
		invoice = self.order(raw)["invoice"]
		frappe.db.commit()
		resolve, counter = self._touch_invoice(invoice, times=1)
		with patch.object(self_ordering, "_resolve_or_create_pos_invoice", resolve):
			add_customer_items(raw, [{"item": ALCOHOL_ITEM, "qty": 1}], age_confirmed=1)
		self.assertEqual(counter["n"], 1)
		self.assertEqual(self._rows(invoice), 2)
		self.assertTrue(get_customer_menu(raw)["age_confirmed"])


class TestTheAnswerIsKeptWhenGiven(SelfOrderingCase):
	"""「はい」 is recorded on the session when it is given, not when the order is sent: a guest who answers and
	reloads the page is not asked again. Only the guest's own session, and only to "yes"."""

	def _recorded(self, raw_session):
		import hashlib

		token_hash = hashlib.sha256(raw_session.encode()).hexdigest()
		return frappe.db.get_value("URY Ordering Session", {"token_hash": token_hash}, "age_confirmed")

	def test_the_answer_is_recorded_without_an_order(self):
		self.staff_open()
		session = self.scan()
		self.assertFalse(get_customer_menu(session)["age_confirmed"])
		result = self_ordering.confirm_age(session)
		self.assertTrue(result["age_confirmed"])
		self.assertTrue(self._recorded(session))
		self.assertTrue(get_customer_menu(session)["age_confirmed"])  # what a reloaded page reads
		self.assertIsNone(frappe.db.get_value("URY Ordering Session", {"token_hash": __import__("hashlib").sha256(session.encode()).hexdigest()}, "invoice"))

	def test_the_order_after_it_needs_no_answer(self):
		self.staff_open()
		session = self.scan()
		self_ordering.confirm_age(session)
		self.assertTrue(add_customer_items(session, [{"item": ALCOHOL_ITEM, "qty": 1}])["invoice"])

	def test_it_is_only_the_session_of_the_guest(self):
		self.staff_open()
		mine, other = self.scan(), self.scan()
		self_ordering.confirm_age(mine)
		self.assertTrue(self._recorded(mine))
		self.assertFalse(self._recorded(other))
		self.refused("Age confirmation required", add_customer_items, other, [{"item": ALCOHOL_ITEM, "qty": 1}])

	def test_it_cannot_be_called_for_a_session_that_is_not_valid(self):
		with self.assertRaises((frappe.ValidationError, frappe.PermissionError)):
			self_ordering.confirm_age("not-a-session")
		self.staff_open()
		old = self.scan()
		self.staff_close()
		self.staff_open()
		self.refused("Table closed", self_ordering.confirm_age, old)
		self.assertFalse(self._recorded(old))

	def test_the_new_guests_of_a_reopened_table_are_asked_again(self):
		self.staff_open()
		old = self.scan()
		self_ordering.confirm_age(old)
		self.staff_close()
		self.staff_open()
		new = self.scan()
		self.assertFalse(get_customer_menu(new)["age_confirmed"])
		self.refused("Age confirmation required", add_customer_items, new, [{"item": ALCOHOL_ITEM, "qty": 1}])

	def test_a_guest_cannot_take_the_answer_back_or_set_anything_else(self):
		# the function has no argument but the session: nothing to send but "yes" for this session
		import inspect

		self.assertEqual(list(inspect.signature(self_ordering.confirm_age).parameters), ["session"])


class TestTheAgeGroupOfExistingProfiles(SelfOrderingCase):
	"""The patch gives a profile that was made before the age check the alcohol group, and leaves the others."""

	def _rows(self):
		return frappe.get_all("URY Age Check Item Group", filters={"parent": PROFILE}, pluck="item_group")

	def _set(self, groups):
		profile = frappe.get_doc("URY Self Ordering Profile", PROFILE)
		profile.set("age_check_item_groups", [{"item_group": group} for group in groups])
		profile.flags.no_default_age_groups = True
		profile.save(ignore_permissions=True)
		frappe.db.commit()

	def test_an_empty_profile_gets_the_alcohol_group(self):
		from ury.patches.v2_0 import age_check_item_groups
		from ury.setup.jp_tax import ALCOHOL_GROUP

		self._set([])
		self.assertEqual(self._rows(), [])
		age_check_item_groups.execute()
		self.assertEqual(self._rows(), [ALCOHOL_GROUP])

	def test_a_profile_with_groups_is_left_alone(self):
		from ury.patches.v2_0 import age_check_item_groups

		self._set(["Consumable"])
		age_check_item_groups.execute()
		self.assertEqual(self._rows(), ["Consumable"])

	def test_running_it_twice_changes_nothing(self):
		from ury.patches.v2_0 import age_check_item_groups
		from ury.setup.jp_tax import ALCOHOL_GROUP

		self._set([])
		age_check_item_groups.execute()
		age_check_item_groups.execute()
		self.assertEqual(self._rows(), [ALCOHOL_GROUP])


class TestWhenBillsAreMerged(SelfOrderingCase):
	"""会計合算 (`merge_bills`): the guests are going to pay together, so the tables of both bills stop taking
	orders from the phones (a guest who wants more asks the staff, who add it in the POS). Putting tables together
	(合桌) does not: the guests still sit there."""

	def setUp(self):
		super().setUp()
		self.staff_open(TABLE)
		self.staff_open(OTHER_TABLE)
		self.first_session, self.second_session = self.scan(TABLE), self.scan(OTHER_TABLE)
		self.first = self.order(self.first_session)["invoice"]
		self.second = self.order(self.second_session)["invoice"]

	def merge(self):
		with as_user(CASHIER):
			result = merge_bills(self.first, self.second)
		self.assertEqual(result["status"], "success", result)

	def test_both_tables_are_closed(self):
		self.merge()
		self.assertFalse(table_row(TABLE)["self_order_open"])
		self.assertFalse(table_row(OTHER_TABLE)["self_order_open"])

	def test_the_guests_of_both_tables_cannot_order_any_more(self):
		self.merge()
		self.refused("Table closed", self.order, self.first_session)
		self.refused("Table closed", self.order, self.second_session)
		self.assertEqual(frappe.db.count("POS Invoice Item", {"parent": self.first}), 1)
		self.assertEqual(frappe.db.count("POS Invoice Item", {"parent": self.second}), 1)

	def test_the_guests_can_still_see_their_order(self):
		self.merge()
		self.assertEqual(len(get_customer_order(self.first_session)["items"]), 1)
		self.assertTrue(get_order_status(self.first_session)["invoice"])

	def test_the_status_says_the_table_is_closed(self):
		self.merge()
		self.assertFalse(get_order_status(self.first_session)["table_open"])

	def test_a_table_that_was_not_merged_stays_open(self):
		self.staff_open(TABLES[2])
		self.merge()
		self.assertTrue(table_row(TABLES[2])["self_order_open"])

	def test_the_staff_can_still_add_dishes_in_the_pos(self):
		self.merge()
		place_order(CAPTAIN, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)], table=TABLE, invoice=self.first)
		self.assertEqual(frappe.db.count("POS Invoice Item", {"parent": self.first}), 2)

	def test_the_table_can_be_opened_again_for_the_next_guests_after_it_is_free(self):
		self.merge()
		self.staff_close(TABLE)
		self.assertFalse(table_row(TABLE)["self_order_open"])

	def test_a_failed_merge_closes_nothing(self):
		with as_user(CASHIER):
			result = merge_bills(self.first, self.first)
		self.assertEqual(result["status"], "error")
		self.assertTrue(table_row(TABLE)["self_order_open"])
		self.assertTrue(table_row(OTHER_TABLE)["self_order_open"])

	def test_bills_without_a_table_can_still_be_merged(self):
		a = place_order(CASHIER, [(FOOD_ITEM, 1)], order_type="Take Away")
		b = place_order(CASHIER, [(FOOD_ITEM, 1)], order_type="Take Away")
		with as_user(CASHIER):
			self.assertEqual(merge_bills(a, b)["status"], "success")
		self.assertTrue(table_row(TABLE)["self_order_open"])


class TestWhenTheStaffAndTheGuestSaveTogether(SelfOrderingCase):
	"""The guest added a dish after the waiter opened the order: the waiter's save is refused ('Order has been
	modified'), the POS reloads, and the guest's dish is still there."""

	def setUp(self):
		super().setUp()
		self.staff_open()
		self.session = self.scan()
		self.invoice = self.order(self.session)["invoice"]

	def rows(self):
		return frappe.get_all("POS Invoice Item", filters={"parent": self.invoice}, pluck="item_code", order_by="idx")

	def test_a_save_with_the_time_before_the_guests_dish_is_refused_and_loses_nothing(self):
		seen = frappe.db.get_value("POS Invoice", self.invoice, "modified")
		frappe.db.set_value("POS Invoice", self.invoice, "modified", add_to_date(seen, seconds=-5), update_modified=False)
		seen = frappe.db.get_value("POS Invoice", self.invoice, "modified")  # what the waiter's screen shows
		self.order(self.session)  # the guest adds a dish: the order changes
		self.assertNotEqual(frappe.db.get_value("POS Invoice", self.invoice, "modified"), seen)
		with self.assertRaises(frappe.ValidationError):
			place_order(CAPTAIN, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)], table=TABLE, invoice=self.invoice, last_modified_time=seen)
		self.assertEqual(self.rows(), [FOOD_ITEM, FOOD_ITEM])

	def test_after_the_reload_the_waiters_save_goes_through_with_the_guests_dish(self):
		self.order(self.session)
		modified = frappe.db.get_value("POS Invoice", self.invoice, "modified")  # what a reload shows
		place_order(CAPTAIN, [(FOOD_ITEM, 2), (ALCOHOL_ITEM, 1)], table=TABLE, invoice=self.invoice, last_modified_time=modified)
		quantity = dict(frappe.db.sql(
			"select item_code, sum(qty) from `tabPOS Invoice Item` where parent=%s group by item_code", self.invoice
		))
		self.assertEqual({k: float(v) for k, v in quantity.items()}, {FOOD_ITEM: 2.0, ALCOHOL_ITEM: 1.0})


class TestTheMenuOfTheGuests(SelfOrderingCase):
	"""The guests are shown the active menu of the restaurant, for a table (Dine In) and for a pickup (Take Away)
	alike: `_customer_menu` asks `resolve_restaurant_menu` with `cashier=False`, which never looks at
	「按订单类型选菜单」 (`order_type_wise_menu`). The shop has it off. If self ordering ever offers pickup or a
	menu of its own per order type, this has to be fixed first (docs/design/self-order-design.md, 5.1 item 6)."""

	def test_with_the_switch_off_the_active_menu_is_used(self):
		frappe.db.set_value("URY Restaurant", RESTAURANT, "order_type_wise_menu", 0)
		active = frappe.db.get_value("URY Restaurant", RESTAURANT, "active_menu")
		profile = frappe.get_doc("URY Self Ordering Profile", PROFILE)
		for order_type in ("Dine In", "Take Away"):
			self.assertEqual(_customer_menu(profile, order_type)["name"], active, order_type)


class TestAfterABillIsSplitWhileTheGuestsAreOrdering(SelfOrderingCase):
	"""拆单 while the table is open: the guests keep ordering on their own order (the original); the order that was
	split off keeps its dishes and its amount, has no session, and the page tells the guests that the bill is
	now in parts."""

	def setUp(self):
		super().setUp()
		from ury.ury.doctype.ury_order.ury_order import split_bill

		self.staff_open()
		self.session = self.scan()
		self.source = add_customer_items(self.session, [{"item": FOOD_ITEM, "qty": 1}, {"item": ALCOHOL_ITEM, "qty": 1, "comment": ""}], 1)["invoice"]
		self.row = frappe.get_all("POS Invoice Item", filters={"parent": self.source, "item_code": ALCOHOL_ITEM}, pluck="name")[0]
		self.split = lambda: self._split(split_bill)

	def _split(self, split_bill):
		with as_user(CASHIER):
			self.sibling = split_bill(self.source, [{"name": self.row, "qty": 1}])["new_invoice"]
		frappe.db.commit()
		self.sibling_items = items_of(self.sibling)
		self.sibling_total = frappe.db.get_value("POS Invoice", self.sibling, "grand_total")

	def test_the_status_says_split_only_after_the_split(self):
		self.assertFalse(get_order_status(self.session).get("split"))
		self.split()
		self.assertTrue(get_order_status(self.session)["split"])

	def test_when_the_part_that_was_split_off_is_cancelled_it_is_not_split_any_more(self):
		self.split()
		with as_user(CASHIER):
			cancel_order(self.sibling, "test")
		self.assertFalse(get_order_status(self.session)["split"])
		self.assertFalse(get_customer_order(self.session)["split"])

	def test_the_order_the_page_shows_says_split_too(self):
		# the page reads the order, not the status
		self.assertFalse(get_customer_order(self.session).get("split"))
		self.split()
		self.assertTrue(get_customer_order(self.session)["split"])

	def test_a_table_that_was_never_split_does_not_say_split(self):
		other = self.scan(OTHER_TABLE) if self.staff_open(OTHER_TABLE) else None
		self.order(other)
		self.assertFalse(get_order_status(other).get("split"))

	def test_what_the_guests_add_goes_to_the_original_and_the_new_order_is_untouched(self):
		self.split()
		order = add_customer_items(self.session, [{"item": FOOD_ITEM, "qty": 1}])
		self.assertEqual(order["invoice"], self.source)
		self.assertEqual(items_of(self.sibling), self.sibling_items)
		self.assertEqual(frappe.db.get_value("POS Invoice", self.sibling, "grand_total"), self.sibling_total)

	def test_the_guests_see_only_the_part_that_stayed(self):
		self.split()
		seen = get_customer_order(self.session)
		self.assertEqual([row["item_code"] for row in seen["items"]], [FOOD_ITEM])

	def test_the_table_stays_open(self):
		self.split()
		self.assertTrue(table_row()["self_order_open"])
		self.order(self.session)
		self.assertTrue(table_row()["self_order_open"])

	def test_the_kitchen_gets_only_the_new_dish(self):
		self.split()
		before = set(frappe.get_all("URY KOT", filters={"invoice": self.source}, pluck="name"))
		self.order(self.session)
		new = [k for k in frappe.get_all("URY KOT", filters={"invoice": self.source}, pluck="name") if k not in before]
		self.assertEqual(len(new), 1)
		rows = frappe.get_all("URY KOT Items", filters={"parent": new[0]}, fields=["item", "quantity"])
		self.assertEqual([(r.item, int(r.quantity)) for r in rows], [(FOOD_ITEM, 1)])

	def test_the_new_order_has_no_session(self):
		self.split()
		self.assertFalse(frappe.db.get_value("POS Invoice", self.sibling, "custom_ordering_session"))

	def test_when_the_original_is_printed_and_paid_first_the_table_stays_and_the_session_follows(self):
		# the other part is not printed yet: its guests are still there (test_split_table_release.py has the rest)
		self.split()
		pay_order(self.source, CASHIER)
		self.assertTrue(table_row()["self_order_open"])
		self.assertEqual(frappe.db.get_value("URY Table", TABLE, "occupied"), 1)
		self.assertEqual(self.order(self.session)["invoice"], self.sibling)
		self.assertEqual(frappe.db.get_value("POS Invoice", self.sibling, "docstatus"), 0)


class TestSplittingABillThatIsPrinted(SelfOrderingCase):
	def test_the_table_is_closed_and_the_guests_cannot_order(self):
		from ury.ury.doctype.ury_order.ury_order import split_bill

		self.staff_open()
		session = self.scan()
		source = add_customer_items(session, [{"item": FOOD_ITEM, "qty": 1}, {"item": ALCOHOL_ITEM, "qty": 1}], 1)["invoice"]
		print_bill(source, CASHIER)
		row = frappe.get_all("POS Invoice Item", filters={"parent": source, "item_code": ALCOHOL_ITEM}, pluck="name")[0]
		with as_user(CASHIER):
			split_bill(source, [{"name": row, "qty": 1}])
		self.assertFalse(table_row()["self_order_open"])
		self.refused("Table closed", self.order, session)
