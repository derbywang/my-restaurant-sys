"""「呼び出し」: the guest calls a member of staff from the table (URY Service Request, type Assistance).

The guest presses the button on the ordering page (QR on the table, or the table tablet); the staff of the branch are told
like for a bill call, and a member of staff answers with 「対応済み」. Unlike the bill, nothing resolves it by itself (the
bill being printed has nothing to do with it), and it does not need an order: a guest may call before ordering anything.

The switch is the Self Ordering Profile's `enable_call_staff` (it exists after the migrate of 2026-11); until then the
tests replace the one function that reads it (`call_staff_enabled`). Test site only.
"""

import datetime
from unittest import mock

import frappe
from frappe.utils import now_datetime

from ury.ury.api import self_ordering
from ury.ury.api.service_requests import get_open_service_requests, resolve_assistance
from ury.ury.api.test_self_ordering_table import PROFILE, TABLE, SelfOrderingCase
from ury.ury.api.test_service_requests import make_request, status_of
from ury.setup.test_site import CAPTAIN, CASHIER, FOOD_ITEM, TABLES, URYFlowTestCase, as_user, place_order

PUBLISH = "ury.ury.api.service_requests.publish_to_branch"


class CallStaffCase(SelfOrderingCase):
	def setUp(self):
		super().setUp()
		patcher = mock.patch.object(self_ordering, "call_staff_enabled", lambda profile: self.enabled)
		self.enabled = True
		patcher.start()
		self.addCleanup(patcher.stop)
		self.staff_open()
		self.session = self.scan()

	def calls(self, table=TABLE):
		return frappe.get_all(
			"URY Service Request", filters={"table": table, "request_type": "Assistance", "status": ["!=", "Resolved"]}, pluck="name"
		)


class TestTheGuestCalls(CallStaffCase):
	def test_a_call_before_any_order_is_an_open_assistance_request_of_the_table(self):
		answer = self_ordering.request_assistance(self.session)
		self.assertEqual(answer["status"], "Requested")
		row = frappe.db.get_value("URY Service Request", answer["request"], ["request_type", "status", "table", "invoice", "session"], as_dict=True)
		self.assertEqual((row.request_type, row.status, row.table, row.invoice), ("Assistance", "Open", TABLE, None))
		self.assertEqual(row.session, self_ordering._resolve_session(self.session).name)

	def test_a_call_after_an_order_names_the_order_too(self):
		invoice = self.order(self.session)["invoice"]
		answer = self_ordering.request_assistance(self.session)
		self.assertEqual(frappe.db.get_value("URY Service Request", answer["request"], "invoice"), invoice)

	def test_pressing_twice_is_one_call(self):
		first = self_ordering.request_assistance(self.session)
		second = self_ordering.request_assistance(self.session)
		self.assertEqual(second["status"], "Already Requested")
		self.assertEqual(second["request"], first["request"])
		self.assertEqual(len(self.calls()), 1)

	def test_the_staff_are_told_after_the_commit(self):
		with mock.patch(PUBLISH) as publish:
			self_ordering.request_assistance(self.session)
		args = publish.call_args
		self.assertEqual(args.args[0], "service_request")
		self.assertEqual((args.args[1]["kind"], args.args[1]["request_type"], args.args[1]["table"]), ("new", "Assistance", TABLE))
		self.assertTrue(args.kwargs.get("after_commit"))

	def test_it_is_refused_when_the_shop_has_not_switched_it_on(self):
		self.enabled = False
		with self.assertRaises(frappe.ValidationError):
			self_ordering.request_assistance(self.session)
		self.assertEqual(self.calls(), [])

	def test_a_session_without_a_table_cannot_call(self):
		with mock.patch.object(self_ordering, "_resolve_session") as resolve:
			resolve.return_value = frappe._dict(table=None, invoice=None, ordering_profile=PROFILE, name="S")
			with self.assertRaises(frappe.ValidationError):
				self_ordering.request_assistance("S")

	def test_a_bill_call_and_a_staff_call_are_two_requests(self):
		self.order(self.session)
		self_ordering.request_assistance(self.session)
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, "enable_request_bill", 1)
		self_ordering.request_bill(self.session)
		kinds = frappe.get_all("URY Service Request", filters={"table": TABLE, "status": "Open"}, pluck="request_type")
		self.assertCountEqual(kinds, ["Assistance", "Bill"])


class TestThePageIsTold(CallStaffCase):
	def test_the_page_learns_whether_to_show_the_button(self):
		from ury.ury.api.self_ordering import generate_qr_token, get_ordering_context

		with as_user("Administrator"):
			token = generate_qr_token(PROFILE, TABLE)
		self.assertTrue(get_ordering_context(token=token)["capabilities"]["call_staff_enabled"])
		self.enabled = False
		self.assertFalse(get_ordering_context(token=token)["capabilities"]["call_staff_enabled"])

	def test_the_open_call_is_in_the_order_status_even_without_an_order(self):
		answer = self_ordering.request_assistance(self.session)
		status = self_ordering.get_order_status(self.session)
		self.assertEqual([r["name"] for r in status["open_requests"]], [answer["request"]])
		self.assertEqual(status["open_requests"][0]["request_type"], "Assistance")

	def test_a_call_of_another_session_at_the_same_table_is_not_shown_to_this_guest(self):
		other = self.scan()
		self_ordering.request_assistance(other)
		self.assertEqual(self_ordering.get_order_status(self.session).get("open_requests", []), [])


class TestTheStaffAnswers(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		from ury.setup.test_site import open_pos

		open_pos(CASHIER)
		self.name = make_request(None, TABLES[0], request_type="Assistance")

	def test_the_waiter_and_the_cashier_mark_it_done(self):
		for user in (CAPTAIN, CASHIER):
			name = make_request(None, TABLES[0], request_type="Assistance")
			with as_user(user):
				self.assertEqual(resolve_assistance(name), {"resolved": 1})
			self.assertEqual(status_of(name), "Resolved")
			row = frappe.db.get_value("URY Service Request", name, ["resolved_by", "resolved_at"], as_dict=True)
			self.assertEqual(row.resolved_by, user)
			self.assertTrue(row.resolved_at)

	def test_the_staff_are_told_it_is_resolved(self):
		with mock.patch(PUBLISH) as publish, as_user(CAPTAIN):
			resolve_assistance(self.name)
		self.assertEqual(publish.call_args.args[1]["kind"], "resolved")

	def test_doing_it_twice_is_harmless_and_tells_nobody(self):
		with as_user(CAPTAIN):
			resolve_assistance(self.name)
		with mock.patch(PUBLISH) as publish, as_user(CAPTAIN):
			self.assertEqual(resolve_assistance(self.name), {"resolved": 0})
		publish.assert_not_called()

	def test_a_bill_request_is_not_resolved_this_way(self):
		invoice = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[1])
		bill = make_request(invoice, TABLES[1], request_type="Bill")
		with as_user(CAPTAIN):
			with self.assertRaises(frappe.ValidationError):
				resolve_assistance(bill)
		self.assertEqual(status_of(bill), "Open")

	def test_a_call_of_another_branch_cannot_be_answered(self):
		with mock.patch("ury.ury.api.service_requests.getBranch", return_value="another branch"), as_user(CAPTAIN):
			with self.assertRaises(frappe.PermissionError):
				resolve_assistance(self.name)
		self.assertEqual(status_of(self.name), "Open")

	def test_a_guest_cannot(self):
		with as_user("Guest"):
			with self.assertRaises(frappe.PermissionError):
				resolve_assistance(self.name)

	def test_opening_the_order_makes_the_call_quiet_but_it_stays_until_answered(self):
		from ury.ury.api.service_requests import acknowledge_requests_of_table

		with as_user(CAPTAIN):
			acknowledge_requests_of_table(TABLES[0])
		self.assertEqual(status_of(self.name), "Acknowledged")
		with as_user(CAPTAIN):
			self.assertIn(self.name, [r["name"] for r in get_open_service_requests()])

	def test_a_call_nobody_answered_for_three_hours_is_not_listed_any_more(self):
		stale = make_request(None, TABLES[1], request_type="Assistance", ago_seconds=3 * 3600 + 60)
		with as_user(CAPTAIN):
			names = [r["name"] for r in get_open_service_requests()]
		self.assertIn(self.name, names)
		self.assertNotIn(stale, names)
