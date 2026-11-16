"""The kitchen error reminder has a second way to reach the register: the register asks now and then.

The reminder is sent in real time on `kot_error_<branch>_<production unit>`. A register whose connection dropped (an
iPad that slept) never hears it. So `publish_to_branch` also keeps the last alerts of the branch for an hour, and
`get_recent_kot_alerts` hands the ones the register has not seen. Run on the test site only.
"""

from unittest.mock import patch

import frappe

from ury.ury.api import branch_realtime
from ury.ury.api.kot_alerts import get_recent_kot_alerts
from ury.setup.test_site import BRANCH, CAPTAIN, CASHIER, URYFlowTestCase, as_user


def alert(invoice="INV-1", unit="Kitchen", kind=None):
	message = {"invoice": invoice, "branch": BRANCH, "production": unit}
	if kind:
		message["kind"] = kind
	return message


class TestKotAlertFallback(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		branch_realtime.forget_kot_alerts(BRANCH)
		branch_realtime.forget_kot_alerts("別の店")
		self.addCleanup(branch_realtime.forget_kot_alerts, BRANCH)
		self.addCleanup(branch_realtime.forget_kot_alerts, "別の店")

	def publish(self, message, branch=BRANCH, event=None):
		with patch("frappe.publish_realtime") as sent:
			branch_realtime.publish_to_branch(event or f"kot_error_{branch}_{message.get('production')}", message, branch)
		return sent

	def recent(self, user=CASHIER, since=0):
		with as_user(user):
			return get_recent_kot_alerts(since=since)

	def test_the_register_that_missed_the_message_finds_it(self):
		self.publish(alert("INV-7"))
		found = self.recent()
		self.assertEqual([a["payload"]["invoice"] for a in found], ["INV-7"])

	def test_the_realtime_message_carries_the_same_id(self):
		sent = self.publish(alert("INV-8"))
		ids = {call.args[1]["alert_id"] for call in sent.call_args_list}
		self.assertEqual(ids, {self.recent()[0]["alert_id"]})

	def test_the_same_alert_on_the_channel_of_each_kitchen_is_one_alert(self):
		self.publish(alert("INV-9", unit="Kitchen A"))
		self.publish(alert("INV-9", unit="Kitchen B"))
		self.assertEqual(len(self.recent()), 1)

	def test_two_different_orders_are_two_alerts(self):
		self.publish(alert("INV-1"))
		self.publish(alert("INV-2"))
		self.assertEqual(len(self.recent()), 2)

	def test_only_what_is_new_since_the_last_look(self):
		self.publish(alert("INV-1"))
		first = self.recent()
		self.publish(alert("INV-2"))
		later = self.recent(since=first[-1]["at"])
		self.assertEqual([a["payload"]["invoice"] for a in later], ["INV-2"])

	def test_the_kinds_without_a_log_are_kept_too(self):
		self.publish({"kind": "no_kitchen", "invoice": "INV-3", "table": "T-01", "branch": BRANCH, "production": "K", "items": ["お茶"]})
		self.assertEqual(self.recent()[0]["payload"]["kind"], "no_kitchen")

	def test_another_branch_does_not_see_it(self):
		self.publish(alert("INV-4"), branch="別の店")
		self.assertEqual(self.recent(), [])

	def test_a_message_of_another_event_is_not_kept(self):
		self.publish({"invoice": "INV-5", "branch": BRANCH}, event="service_request")
		self.assertEqual(self.recent(), [])

	def test_the_waiter_asks_too(self):
		self.publish(alert("INV-6"))
		self.assertEqual(len(self.recent(CAPTAIN)), 1)

	def test_the_first_look_of_a_page_shows_only_the_last_ten_minutes(self):
		# a register that reloads must not replay the alerts of an hour ago
		import time

		self.publish(alert("INV-OLD"))
		real = time.time
		with patch("ury.ury.api.branch_realtime.time.time", lambda: real() + 15 * 60):
			self.publish(alert("INV-NEW"))
			self.assertEqual([a["payload"]["invoice"] for a in self.recent(since=0)], ["INV-NEW"])

	def test_a_guest_cannot_ask(self):
		with as_user("Guest"):
			with self.assertRaises(frappe.PermissionError):
				get_recent_kot_alerts(since=0)
