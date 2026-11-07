"""The rest of what keeps self ordering running by itself (self-order-design 3.5, 3.6).

A profile without a default customer uses the POS Profile's; a kitchen ticket that cannot be made is announced
at the register while the order stays; old sessions of guests who only scanned are cleaned up every day.
Run on the test site only.
"""

from unittest.mock import patch

import frappe
from frappe.utils import add_to_date, now_datetime

from ury.setup.test_site import BRANCH, FOOD_ITEM, POS_PROFILE, PRODUCTION_UNIT, TABLES
from ury.ury.api import self_ordering
from ury.ury.api.test_self_ordering_table import PROFILE, SelfOrderingCase

TABLE = TABLES[0]


class TestDefaultCustomer(SelfOrderingCase):
	def _without_default_customer(self):
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, "default_customer", None)

	def test_a_profile_saved_without_a_customer_gets_the_one_of_the_pos_profile(self):
		doc = frappe.get_doc("URY Self Ordering Profile", PROFILE)
		doc.default_customer = None
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.default_customer, frappe.db.get_value("POS Profile", POS_PROFILE, "customer"))

	def test_an_order_is_taken_when_the_profile_has_no_customer(self):
		self._without_default_customer()
		self.staff_open()
		order = self.order(self.scan())
		self.assertEqual(frappe.db.get_value("POS Invoice", order["invoice"], "customer"), frappe.db.get_value("POS Profile", POS_PROFILE, "customer"))

	def test_the_totals_shown_to_the_guest_work_without_it_too(self):
		self._without_default_customer()
		self.staff_open()
		session = self.scan()
		preview = self_ordering.preview_customer_cart(session, [{"item": FOOD_ITEM, "qty": 1}])
		self.assertTrue(preview["rounded_total"])

	def test_no_customer_anywhere_is_refused_with_a_clear_message(self):
		self._without_default_customer()
		original = frappe.db.get_value("POS Profile", POS_PROFILE, "customer")
		frappe.db.set_value("POS Profile", POS_PROFILE, "customer", None)
		self.addCleanup(lambda: frappe.db.set_value("POS Profile", POS_PROFILE, "customer", original))
		self.staff_open()
		session = self.scan()
		with self.assertRaises(frappe.ValidationError):
			self.order(session)


class TestSecret(SelfOrderingCase):
	def test_a_profile_saved_without_a_secret_gets_one(self):
		doc = frappe.get_doc("URY Self Ordering Profile", PROFILE)
		doc.qr_signing_secret = None
		doc.save(ignore_permissions=True)
		self.assertGreaterEqual(len(doc.qr_signing_secret), 32)

	def test_a_secret_that_is_there_is_not_changed(self):
		doc = frappe.get_doc("URY Self Ordering Profile", PROFILE)
		secret = doc.qr_signing_secret
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.qr_signing_secret, secret)


class TestKotFailure(SelfOrderingCase):
	def _order_when_kot_fails(self):
		self.staff_open()
		session = self.scan()
		with patch("ury.ury.api.self_ordering.kot_execute", side_effect=Exception("printer on fire")), patch(
			"ury.ury.api.self_ordering.frappe.publish_realtime"
		) as publish:
			order = self.order(session)
		return order, publish

	def test_the_order_is_saved_although_the_ticket_failed(self):
		order, _publish = self._order_when_kot_fails()
		self.assertEqual(frappe.db.get_value("POS Invoice", order["invoice"], "docstatus"), 0)
		self.assertEqual(frappe.db.count("POS Invoice Item", {"parent": order["invoice"]}), 1)

	def test_the_register_is_told_on_the_channel_of_every_kitchen_of_the_branch(self):
		order, publish = self._order_when_kot_fails()
		channels = [call.args[0] for call in publish.call_args_list if str(call.args[0]).startswith("kot_error_")]
		self.assertEqual(channels, [f"kot_error_{BRANCH}_{PRODUCTION_UNIT}"])
		call = [c for c in publish.call_args_list if str(c.args[0]).startswith("kot_error_")][0]
		payload = call.args[1]
		self.assertEqual((payload["kind"], payload["invoice"], payload["table"]), ("self_order", order["invoice"], TABLE))
		self.assertTrue(call.kwargs.get("after_commit"))

	def test_the_failure_is_still_logged(self):
		self.staff_open()
		session = self.scan()
		with patch("ury.ury.api.self_ordering.kot_execute", side_effect=Exception("printer on fire")):
			with patch("ury.ury.api.self_ordering.frappe.log_error") as log:
				self.order(session)
		self.assertIn("printer on fire", log.call_args.args[0])

	def test_nothing_is_announced_when_the_ticket_is_made(self):
		self.staff_open()
		session = self.scan()
		with patch("ury.ury.api.self_ordering.frappe.publish_realtime") as publish:
			self.order(session)
		self.assertNotIn("kot_error", " ".join(str(call.args[0]) for call in publish.call_args_list))


class TestOldSessions(SelfOrderingCase):
	def _session(self, status, days_old, invoice=None, expires_in_days=None):
		doc = frappe.get_doc(
			{
				"doctype": "URY Ordering Session",
				"ordering_profile": PROFILE,
				"source": "QR Table",
				"table": TABLE,
				"status": status,
				"token_hash": frappe.generate_hash(length=20),
				"opened_at": add_to_date(now_datetime(), days=-days_old),
				"expires_at": add_to_date(now_datetime(), days=expires_in_days if expires_in_days is not None else -days_old),
				"last_activity": add_to_date(now_datetime(), days=-days_old),
			}
		)
		doc.insert(ignore_permissions=True)
		old = add_to_date(now_datetime(), days=-days_old)
		frappe.db.set_value("URY Ordering Session", doc.name, {"modified": old, "creation": old}, update_modified=False)
		if invoice:
			frappe.db.set_value("URY Ordering Session", doc.name, "invoice", invoice, update_modified=False)
		return doc.name

	def _exists(self, name):
		return bool(frappe.db.exists("URY Ordering Session", name))

	def test_old_expired_and_closed_sessions_are_deleted(self):
		expired, closed = self._session("Expired", 8), self._session("Closed", 30)
		self_ordering.delete_old_sessions()
		self.assertFalse(self._exists(expired))
		self.assertFalse(self._exists(closed))

	def test_recent_ones_stay(self):
		expired, closed = self._session("Expired", 3), self._session("Closed", 6)
		self_ordering.delete_old_sessions()
		self.assertTrue(self._exists(expired))
		self.assertTrue(self._exists(closed))

	def test_a_session_still_active_stays(self):
		active = self._session("Active", 0, expires_in_days=1)
		self_ordering.delete_old_sessions()
		self.assertTrue(self._exists(active))

	def test_an_active_session_that_ran_out_long_ago_is_deleted_too(self):
		"""The status becomes Expired only when the guest comes back; one who never did stays Active."""
		forgotten = self._session("Active", 10)
		self_ordering.delete_old_sessions()
		self.assertFalse(self._exists(forgotten))

	def test_a_session_with_an_order_is_kept_as_the_record_of_it(self):
		self.staff_open()
		invoice = self.order(self.scan())["invoice"]
		kept = self._session("Closed", 40, invoice=invoice)
		self_ordering.delete_old_sessions()
		self.assertTrue(self._exists(kept))

	def test_it_runs_every_day(self):
		from ury import hooks

		self.assertIn("ury.ury.api.self_ordering.delete_old_sessions", hooks.scheduler_events["daily"])


