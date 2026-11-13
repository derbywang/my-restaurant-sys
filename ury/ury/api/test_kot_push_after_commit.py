"""The kitchen screen is told about a ticket only after the ticket is saved for good (2026-11-14).

The push used to go out while the order was still being cancelled (before the commit). The screen, which reads its list
again 1.5 s after a cancel ticket, then got a list without the ticket and replaced what it showed with it: the cancel
ticket of an order that took more than about 1.5 s to cancel never stayed on the screen (INV-00108, 3.8 s).
Run on the test site only (a trial site first)."""

import time
from unittest import mock

import frappe

from ury.setup.test_site import (
	BRANCH,
	CAPTAIN,
	CASHIER,
	FOOD_ITEM,
	POS_PROFILE,
	PRODUCTION_UNIT,
	URYFlowTestCase,
	URYTestCase,
	open_pos,
	place_order,
)
from ury.ury.api.test_realtime_reach import Probe, reachable, unittest_skip


class TestPushIsAfterCommit(URYTestCase):
	def test_the_kitchen_screen_push_waits_for_the_commit(self):
		ticket = frappe.new_doc("URY KOT")
		ticket.update({"branch": BRANCH, "production": PRODUCTION_UNIT, "type": "Cancelled", "time": "12:00:00",
		               "pos_profile": POS_PROFILE})
		with mock.patch("ury.ury.doctype.ury_kot.ury_kot.publish_to_branch") as publish:
			ticket.kotDisplayRealtime()
		self.assertTrue(publish.called)
		self.assertTrue(publish.call_args.kwargs.get("after_commit"), publish.call_args)
		self.assertEqual(publish.call_args.args[0], f"kot_update_{BRANCH}_{PRODUCTION_UNIT}")


class TestTheScreenFindsTheTicketWhenTheyArePushed(URYFlowTestCase):
	"""A real connection: when the push of a cancel ticket arrives, reading the screen's list (as the screen does) must
	already contain that ticket, even when the rest of the cancel takes a while."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not (reachable(8000) and reachable(9000)):
			raise unittest_skip("the web server (8000) or the socketio server (9000) does not answer")

	def test_the_ticket_is_in_the_list_when_the_push_arrives(self):
		from ury.ury.doctype.ury_order.ury_order import cancel_kot

		open_pos(CASHIER)
		invoice = place_order(CASHIER, [(FOOD_ITEM, 1)], order_type="Take Away")
		probe = Probe([CAPTAIN], seconds=6, fetch_prefix="kot_update_")  # the captain stands for the kitchen account
		probe.start()
		try:
			cancel_kot(invoice)
			time.sleep(2.5)  # the rest of the cancel is slow (here: this long before the commit)
			frappe.db.commit()
		finally:
			probe.finish()
		pushed = [e for e in probe.events[CAPTAIN] if e.get("kot", "").startswith("CNCL-")]
		self.assertTrue(pushed, probe.events[CAPTAIN])
		self.assertTrue(all(e["listed"] for e in pushed), pushed)
