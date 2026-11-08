"""How long a table has been occupied: `URY Table.latest_invoice_time` is a Datetime, not a Time.

It used to be a Time field: the date was thrown away, so a bill from yesterday looked like "today at that
clock time" and the service line showed negative minutes before that time of day (2026-11 on the dev site:
-137 and -9, and 1057 for a table left open since 11/04). Run on the test site only.
"""

import importlib

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime

from ury.setup.test_site import (
	BRANCH,
	CAPTAIN,
	CASHIER,
	FOOD_ITEM,
	TABLES,
	URYFlowTestCase,
	as_user,
	open_pos,
	place_order,
	print_bill,
)
from ury.ury.api.ury_dashboard import get_needs_attention
from ury.ury.api.ury_service_line import get_service_line
from ury.ury.doctype.ury_order.ury_order import split_bill, table_seated_at


def clear_dashboard_cache():
	for key in (f"ury_dashboard_service_line:{BRANCH}", f"ury_dashboard_needs_attention:{BRANCH}"):
		frappe.cache().delete_value(key)


class TestTableOpenSince(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		clear_dashboard_cache()
		self.addCleanup(clear_dashboard_cache)

	def _occupy(self, table, opened_at):
		open_pos(CASHIER)
		invoice = place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=table)
		frappe.db.set_value("URY Table", table, "latest_invoice_time", opened_at)
		return invoice

	def test_the_field_is_a_datetime(self):
		self.assertEqual(frappe.get_meta("URY Table").get_field("latest_invoice_time").fieldtype, "Datetime")

	def test_the_date_is_kept(self):
		opened = add_to_date(now_datetime(), days=-2, minutes=-5, as_datetime=True)
		self._occupy(TABLES[0], opened)
		stored = get_datetime(frappe.db.get_value("URY Table", TABLES[0], "latest_invoice_time"))
		self.assertEqual(stored.date(), opened.date())

	def test_a_bill_from_yesterday_shows_its_real_age_not_a_negative_number(self):
		# 26 hours ago: before and after midnight, at any time of day, never negative
		self._occupy(TABLES[0], add_to_date(now_datetime(), hours=-26, as_datetime=True))
		row = next(r for r in get_service_line(branch=BRANCH) if r["table"] == TABLES[0])
		self.assertGreaterEqual(row["minutes"], 26 * 60 - 1)
		self.assertLessEqual(row["minutes"], 26 * 60 + 1)
		self.assertEqual(row["stage"], "over")

	def test_a_bill_of_ten_minutes_ago(self):
		self._occupy(TABLES[0], add_to_date(now_datetime(), minutes=-10, as_datetime=True))
		row = next(r for r in get_service_line(branch=BRANCH) if r["table"] == TABLES[0])
		self.assertIn(row["minutes"], (9, 10, 11))
		self.assertNotEqual(row["stage"], "over")

	def test_needs_attention_counts_a_table_open_since_yesterday(self):
		self._occupy(TABLES[0], add_to_date(now_datetime(), hours=-26, as_datetime=True))
		items = get_needs_attention(branch=BRANCH)
		self.assertIn("table_occupied_long", [i["type"] for i in items])

	def test_needs_attention_ignores_a_table_just_seated(self):
		self._occupy(TABLES[0], add_to_date(now_datetime(), minutes=-10, as_datetime=True))
		items = get_needs_attention(branch=BRANCH)
		self.assertNotIn("table_occupied_long", [i["type"] for i in items])


class TestBackfillPatch(URYFlowTestCase):
	"""The patch that turned the Time column into a Datetime: occupied tables get the creation of their open bill,
	free tables get nothing."""

	def setUp(self):
		super().setUp()
		self.module = importlib.import_module("ury.patches.v3_0.latest_invoice_time_datetime")

	def test_an_occupied_table_gets_the_creation_of_its_open_bill(self):
		open_pos(CASHIER)
		invoice = place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLES[0])
		yesterday = add_to_date(now_datetime(), days=-1, hours=-3, as_datetime=True)
		frappe.db.set_value("POS Invoice", invoice, "creation", yesterday, update_modified=False)
		frappe.db.set_value("URY Table", TABLES[0], "latest_invoice_time", now_datetime())  # what the conversion leaves
		self.module.execute()
		self.assertEqual(get_datetime(frappe.db.get_value("URY Table", TABLES[0], "latest_invoice_time")), yesterday)

	def test_a_free_table_gets_nothing(self):
		frappe.db.set_value("URY Table", TABLES[1], {"occupied": 0, "latest_invoice_time": now_datetime()})
		self.module.execute()
		self.assertIsNone(frappe.db.get_value("URY Table", TABLES[1], "latest_invoice_time"))

	def test_an_occupied_table_without_an_open_bill_gets_nothing_and_stays_occupied(self):
		frappe.db.set_value("URY Table", TABLES[2], {"occupied": 1, "latest_invoice_time": now_datetime()})
		self.module.execute()
		self.assertIsNone(frappe.db.get_value("URY Table", TABLES[2], "latest_invoice_time"))
		self.assertEqual(frappe.db.get_value("URY Table", TABLES[2], "occupied"), 1)

	def test_a_table_merged_into_a_bill_gets_its_creation_too(self):
		open_pos(CASHIER)
		invoice = place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLES[0])
		yesterday = add_to_date(now_datetime(), days=-1, hours=-3, as_datetime=True)
		frappe.db.set_value("POS Invoice", invoice, {"creation": yesterday, "custom_merged_tables": f"{TABLES[1]}, {TABLES[2]}"}, update_modified=False)
		frappe.db.set_value("URY Table", TABLES[1], {"occupied": 1, "latest_invoice_time": now_datetime()})
		self.module.execute()
		self.assertEqual(get_datetime(frappe.db.get_value("URY Table", TABLES[1], "latest_invoice_time")), yesterday)

	def test_a_split_bill_counts_from_the_first_bill_of_its_group(self):
		open_pos(CASHIER)
		first = place_order(CASHIER, [(FOOD_ITEM, 2)], table=TABLES[0])
		print_bill(first)
		row = frappe.db.get_value("POS Invoice Item", {"parent": first, "item_code": FOOD_ITEM}, "name")
		with as_user(CASHIER):
			second = split_bill(first, [{"name": row, "qty": 1}])["new_invoice"]
		seated = add_to_date(now_datetime(), days=-1, hours=-3, as_datetime=True)
		frappe.db.set_value("POS Invoice", first, "creation", seated, update_modified=False)
		# printing the first bill freed the table; the guests ordering on the new bill occupy it again
		frappe.db.set_value("URY Table", TABLES[0], {"occupied": 1, "latest_invoice_time": now_datetime()})
		self.module.execute()
		self.assertEqual(get_datetime(frappe.db.get_value("URY Table", TABLES[0], "latest_invoice_time")), seated)
		self.assertGreater(get_datetime(frappe.db.get_value("POS Invoice", second, "creation")), seated)

	def test_new_guests_after_an_older_printed_bill_count_from_their_own_bill(self):
		# the older bill is printed and not paid, the guests of the newer one are not the same people (no split group)
		open_pos(CASHIER)
		older = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])
		print_bill(older)
		newer = place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLES[0])
		self.assertNotEqual(older, newer)
		frappe.db.set_value("POS Invoice", older, "creation", add_to_date(now_datetime(), days=-1, as_datetime=True), update_modified=False)
		frappe.db.set_value("URY Table", TABLES[0], "latest_invoice_time", now_datetime())
		self.module.execute()
		self.assertEqual(
			get_datetime(frappe.db.get_value("URY Table", TABLES[0], "latest_invoice_time")),
			get_datetime(frappe.db.get_value("POS Invoice", newer, "creation")),
		)

	def test_it_can_run_twice(self):
		open_pos(CASHIER)
		invoice = place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLES[0])
		before = frappe.db.get_value("POS Invoice", invoice, "creation")
		self.module.execute()
		self.module.execute()
		self.assertEqual(get_datetime(frappe.db.get_value("URY Table", TABLES[0], "latest_invoice_time")), get_datetime(before))


def seat_time(table):
	return get_datetime(frappe.db.get_value("URY Table", table, "latest_invoice_time"))


class TestSplitKeepsTheSeatTime(URYFlowTestCase):
	"""The time of a table is when its guests sat down. A split makes new bills for the same guests, so neither the
	split nor an order added to the new bill may start the clock again."""

	def _printed_bill_from_two_hours_ago(self):
		open_pos(CASHIER)
		bill = place_order(CASHIER, [(FOOD_ITEM, 2)], table=TABLES[0])
		print_bill(bill)
		seated = add_to_date(now_datetime(), hours=-2, as_datetime=True)
		frappe.db.set_value("POS Invoice", bill, "creation", seated, update_modified=False)
		frappe.db.set_value("URY Table", TABLES[0], "latest_invoice_time", seated)
		return bill, seated

	def _split(self, bill):
		row = frappe.db.get_value("POS Invoice Item", {"parent": bill, "item_code": FOOD_ITEM}, "name")
		with as_user(CASHIER):
			return split_bill(bill, [{"name": row, "qty": 1}])["new_invoice"]

	def test_splitting_does_not_move_the_time(self):
		bill, seated = self._printed_bill_from_two_hours_ago()
		self._split(bill)
		self.assertEqual(seat_time(TABLES[0]), seated)

	def test_adding_to_the_new_bill_does_not_move_the_time(self):
		bill, seated = self._printed_bill_from_two_hours_ago()
		new = self._split(bill)
		modified = frappe.db.get_value("POS Invoice", new, "modified")
		place_order(CASHIER, [(FOOD_ITEM, 2)], table=TABLES[0], invoice=new, last_modified_time=modified)
		self.assertEqual(frappe.db.get_value("POS Invoice Item", {"parent": new}, "qty"), 2)  # it really was updated
		self.assertEqual(seat_time(TABLES[0]), seated)

	def test_the_seat_time_of_a_split_bill_is_that_of_the_first_bill_of_its_group(self):
		bill, seated = self._printed_bill_from_two_hours_ago()
		new = self._split(bill)
		self.assertGreater(get_datetime(frappe.db.get_value("POS Invoice", new, "creation")), seated)
		self.assertEqual(get_datetime(table_seated_at(frappe.get_doc("POS Invoice", new))), seated)
		self.assertEqual(get_datetime(table_seated_at(frappe.get_doc("POS Invoice", bill))), seated)

	def test_a_bill_without_a_split_group_is_seated_when_it_was_created(self):
		open_pos(CASHIER)
		bill = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])
		doc = frappe.get_doc("POS Invoice", bill)
		self.assertFalse(doc.get("custom_split_group"))
		self.assertEqual(table_seated_at(doc), doc.creation)
