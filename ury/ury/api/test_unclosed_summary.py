"""The opening screen warns about invoices that were never closed (2026-11-14).

The closing of a shift covers every unconsolidated invoice of the POS Profile (docs/design/pos-closing.md), so after a
forgotten closing the next one holds two days of sales. The opening screen of the next cashier is told how many
invoices wait, how much they are and since when, and asks for a confirmation before the register is opened.
Run on the test site only.
"""

from datetime import timedelta

import frappe
from frappe.utils import now_datetime

from ury.ury.api.pos_closing import unclosed_summary
from ury.ury_pos.api import get_pos_opening_screen_data as OPENING_SCREEN
from ury.setup.test_site import CASHIER, FOOD_ITEM, POS_PROFILE, TABLES, URYFlowTestCase, as_user, open_pos, pay_order, place_order


class TestUnclosedSummary(URYFlowTestCase):
	def _paid_at(self, when, table=0):
		order = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[table])
		pay_order(order)
		frappe.db.set_value(
			"POS Invoice",
			order,
			# a string: a time object would lose the microseconds the real posting times have
			{"posting_date": when.date(), "posting_time": when.strftime("%H:%M:%S.%f")},
			update_modified=False,
		)
		return order

	def setUp(self):
		super().setUp()
		open_pos(CASHIER)
		self.yesterday = now_datetime().replace(hour=19, minute=0, second=0, microsecond=0) - timedelta(days=1)
		self.before_yesterday = self.yesterday - timedelta(days=1)

	def test_nothing_is_unclosed_when_there_are_no_invoices(self):
		self.assertIsNone(unclosed_summary(POS_PROFILE))

	def test_the_count_the_total_and_the_oldest_date(self):
		a = self._paid_at(self.before_yesterday, 0)
		b = self._paid_at(self.yesterday, 1)
		total = sum(frappe.db.get_value("POS Invoice", n, "grand_total") for n in (a, b))

		summary = unclosed_summary(POS_PROFILE)

		self.assertEqual(summary["count"], 2)
		self.assertEqual(summary["total"], total)
		self.assertEqual(summary["oldest_date"], str(self.before_yesterday.date()))

	def test_a_consolidated_invoice_does_not_count(self):
		a = self._paid_at(self.yesterday, 0)
		frappe.db.set_value("POS Invoice", a, {"consolidated_invoice": "SINV-X", "status": "Consolidated"})
		self.assertIsNone(unclosed_summary(POS_PROFILE))

	def test_an_invoice_of_another_pos_profile_does_not_count(self):
		a = self._paid_at(self.yesterday, 0)
		frappe.db.set_value("POS Invoice", a, "pos_profile", "no-such-profile")
		self.assertIsNone(unclosed_summary(POS_PROFILE))

	def test_a_draft_does_not_count(self):
		place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])
		self.assertIsNone(unclosed_summary(POS_PROFILE))

	def test_an_invoice_after_the_given_time_does_not_count(self):
		self._paid_at(self.yesterday, 0)
		self.assertIsNone(unclosed_summary(POS_PROFILE, before=self.before_yesterday))

	def test_the_opening_screen_carries_the_summary(self):
		a = self._paid_at(self.yesterday, 0)
		with as_user(CASHIER):
			data = OPENING_SCREEN()
		self.assertEqual(data["unclosed_invoices"]["count"], 1)
		self.assertEqual(data["unclosed_invoices"]["total"], frappe.db.get_value("POS Invoice", a, "grand_total"))

	def test_the_opening_screen_has_no_summary_when_everything_is_closed(self):
		with as_user(CASHIER):
			data = OPENING_SCREEN()
		self.assertIn("unclosed_invoices", data)
		self.assertIsNone(data["unclosed_invoices"])

	def test_the_question_changes_nothing(self):
		self._paid_at(self.yesterday, 0)
		before = frappe.db.count("POS Invoice")
		unclosed_summary(POS_PROFILE)
		self.assertEqual(frappe.db.count("POS Invoice"), before)
