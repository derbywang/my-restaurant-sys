"""「お会計」 (call for the bill) requests as the POS sees them (docs/design/self-order-design.md 3.8).

States: Open (nobody looked yet: the POS rings), Acknowledged (a member of staff opened the table's order: quiet, but the
table card keeps the bell and the waiting time), Resolved (bill printed, paid or cancelled: gone from the POS).
"""

import datetime
from unittest import mock

import frappe
from frappe.utils import now_datetime

from ury.setup.test_site import (
	BRANCH,
	CAPTAIN,
	CASHIER,
	FOOD_ITEM,
	TABLES,
	URYFlowTestCase,
	as_user,
	open_pos,
	pay_order,
	place_order,
	print_bill,
)

PUBLISH = "ury.ury.api.service_requests.publish_to_branch"


def make_request(invoice, table, status="Open", request_type="Bill", ago_seconds=0):
	doc = frappe.get_doc(
		{
			"doctype": "URY Service Request",
			"request_type": request_type,
			"table": table,
			"invoice": invoice,
			"status": status,
			"requested_at": now_datetime() - datetime.timedelta(seconds=ago_seconds),
		}
	)
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return doc.name


def status_of(name):
	return frappe.db.get_value("URY Service Request", name, "status")


class TestListing(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		open_pos(CASHIER)
		self.invoice = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])
		self.other = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[1])

	def _list(self, user=CAPTAIN):
		from ury.ury.api.service_requests import get_open_service_requests

		with as_user(user):
			return get_open_service_requests()

	def test_open_and_acknowledged_requests_are_listed_resolved_ones_are_not(self):
		a = make_request(self.invoice, TABLES[0], "Open")
		b = make_request(self.other, TABLES[1], "Acknowledged")
		make_request(self.other, TABLES[1], "Resolved")
		rows = self._list()
		self.assertEqual({r["name"] for r in rows}, {a, b})

	def test_a_row_has_what_the_table_card_needs(self):
		name = make_request(self.invoice, TABLES[0], "Open", ago_seconds=125)
		row = self._list()[0]
		self.assertEqual(row["name"], name)
		self.assertEqual(row["request_type"], "Bill")
		self.assertEqual(row["status"], "Open")
		self.assertEqual(row["table"], TABLES[0])
		self.assertEqual(row["room"], frappe.db.get_value("URY Table", TABLES[0], "restaurant_room"))
		self.assertEqual(row["invoice"], self.invoice)
		# the waiting time is counted by the server, so no clock or time zone of the tablet matters
		self.assertGreaterEqual(row["waited_seconds"], 125)
		self.assertLess(row["waited_seconds"], 140)

	def test_the_longest_waiting_comes_first(self):
		new = make_request(self.invoice, TABLES[0], ago_seconds=10)
		old = make_request(self.other, TABLES[1], ago_seconds=200)
		self.assertEqual([r["name"] for r in self._list()], [old, new])

	def test_every_member_of_staff_who_takes_orders_may_read_them(self):
		make_request(self.invoice, TABLES[0])
		self.assertEqual(len(self._list(CAPTAIN)), 1)
		self.assertEqual(len(self._list(CASHIER)), 1)

	def test_a_request_of_a_table_of_another_branch_is_not_listed(self):
		make_request(self.invoice, TABLES[0])
		with mock.patch("ury.ury.api.service_requests.getBranch", return_value="another branch"):
			self.assertEqual(self._list(), [])

	def test_a_guest_may_not_read_them(self):
		make_request(self.invoice, TABLES[0])
		with self.assertRaises(frappe.PermissionError):
			self._list("Guest")


class TestAcknowledge(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		open_pos(CASHIER)
		self.invoice = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])

	def _ack(self, table, user=CAPTAIN):
		from ury.ury.api.service_requests import acknowledge_requests_of_table

		with as_user(user):
			return acknowledge_requests_of_table(table)

	def test_opening_the_order_makes_the_open_request_acknowledged_and_keeps_its_time(self):
		name = make_request(self.invoice, TABLES[0], ago_seconds=90)
		before = frappe.db.get_value("URY Service Request", name, "requested_at")
		with mock.patch(PUBLISH) as publish:
			self._ack(TABLES[0])
		self.assertEqual(status_of(name), "Acknowledged")
		# the waiting time keeps counting from the button the guest pressed
		self.assertEqual(frappe.db.get_value("URY Service Request", name, "requested_at"), before)
		kinds = [call.args[1]["kind"] for call in publish.call_args_list]
		self.assertEqual(kinds, ["acknowledged"])

	def test_it_is_harmless_to_do_twice_and_tells_nobody_the_second_time(self):
		name = make_request(self.invoice, TABLES[0])
		self._ack(TABLES[0])
		with mock.patch(PUBLISH) as publish:
			self._ack(TABLES[0])
		self.assertEqual(status_of(name), "Acknowledged")
		publish.assert_not_called()

	def test_a_resolved_request_stays_resolved(self):
		name = make_request(self.invoice, TABLES[0], "Resolved")
		self._ack(TABLES[0])
		self.assertEqual(status_of(name), "Resolved")

	def test_only_the_requests_of_that_table(self):
		other = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[1])
		mine = make_request(self.invoice, TABLES[0])
		theirs = make_request(other, TABLES[1])
		self._ack(TABLES[0])
		self.assertEqual((status_of(mine), status_of(theirs)), ("Acknowledged", "Open"))

	def test_a_table_of_another_branch_cannot_be_acknowledged(self):
		name = make_request(self.invoice, TABLES[0])
		with mock.patch("ury.ury.api.service_requests.getBranch", return_value="another branch"):
			with self.assertRaises(frappe.PermissionError):
				self._ack(TABLES[0])
		self.assertEqual(status_of(name), "Open")


class TestResolvedByTheBill(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		open_pos(CASHIER)
		self.invoice = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])

	def test_printing_the_bill_resolves_open_and_acknowledged_requests(self):
		a = make_request(self.invoice, TABLES[0], "Open")
		b = make_request(self.invoice, TABLES[0], "Acknowledged")
		with mock.patch(PUBLISH) as publish:
			print_bill(self.invoice)
		self.assertEqual((status_of(a), status_of(b)), ("Resolved", "Resolved"))
		self.assertEqual(frappe.db.get_value("URY Service Request", a, "resolved_by"), CASHIER)
		self.assertTrue(frappe.db.get_value("URY Service Request", a, "resolved_at"))
		self.assertIn("resolved", [call.args[1]["kind"] for call in publish.call_args_list])

	def test_paying_resolves_them(self):
		name = make_request(self.invoice, TABLES[0])
		pay_order(self.invoice)
		self.assertEqual(status_of(name), "Resolved")

	def test_cancelling_the_order_resolves_them(self):
		from ury.ury.doctype.ury_order.ury_order import cancel_order

		name = make_request(self.invoice, TABLES[0])
		with as_user(CASHIER):
			cancel_order(self.invoice, "test")
		self.assertEqual(status_of(name), "Resolved")

	def test_the_request_of_another_order_is_left_alone(self):
		other = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[1])
		mine = make_request(self.invoice, TABLES[0])
		theirs = make_request(other, TABLES[1])
		print_bill(self.invoice)
		self.assertEqual((status_of(mine), status_of(theirs)), ("Resolved", "Open"))

	def test_nothing_is_published_when_there_was_nothing_to_resolve(self):
		with mock.patch(PUBLISH) as publish:
			print_bill(self.invoice)
		publish.assert_not_called()

	def test_an_assistance_request_is_not_resolved_by_the_bill(self):
		name = make_request(self.invoice, TABLES[0], request_type="Assistance")
		print_bill(self.invoice)
		self.assertEqual(status_of(name), "Open")


class TestNewRequestIsPublished(URYFlowTestCase):
	def test_request_bill_tells_the_staff_of_the_branch_after_the_commit(self):
		from ury.ury.api.service_requests import announce

		open_pos(CASHIER)
		invoice = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])
		name = make_request(invoice, TABLES[0])
		with mock.patch(PUBLISH) as publish:
			announce(frappe.get_doc("URY Service Request", name), "new")
		args = publish.call_args
		self.assertEqual(args.args[0], "service_request")
		self.assertEqual(args.args[2], BRANCH)
		self.assertEqual(args.args[1]["kind"], "new")
		self.assertEqual(args.args[1]["table"], TABLES[0])
		self.assertTrue(args.kwargs.get("after_commit"))
