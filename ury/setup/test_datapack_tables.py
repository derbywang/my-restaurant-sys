"""The data pack imports the rooms and the tables (docs/design/data-pack.md, step 3).

`plan_tables` only reads and says what would be created, updated or left; `apply_tables` does it; importing the same
sheets again changes nothing; a table that is in use keeps its state. Everything runs in a rolled-back savepoint.
"""

import frappe

from ury.setup.datapack import importer
from ury.setup.datapack.reader import Row
from ury.setup.test_datapack_menu import RolledBack, pack
from ury.setup.test_site import BRANCH, RESTAURANT

HALL = "DPホール"
PRIVATE = "DP個室"
T1 = "DP-01"
T2 = "DP-02"
T_AWAY = "DP-持ち帰り"
OTHER_BRANCH = "DP別店"


def room(name):
	return {"name": name, "note": None}


def table(name, room_name=HALL, seats=4, take_away=False):
	return {"name": name, "room": room_name, "seats": seats, "take_away": take_away, "note": None}


def rows(*values):
	return [Row(5 + i, v) for i, v in enumerate(values)]


def places(rooms=None, tables=None):
	return pack(
		rooms=rows(*(rooms if rooms is not None else [room(HALL), room(PRIVATE)])),
		tables=rows(*(tables if tables is not None else [table(T1), table(T2, PRIVATE, 6), table(T_AWAY, HALL, None, True)])),
	)


def verbs(result):
	return {(a.doctype, a.name): a.verb for a in result.actions}


def make_other_branch():
	if not frappe.db.exists("Branch", OTHER_BRANCH):
		frappe.get_doc({"doctype": "Branch", "branch": OTHER_BRANCH, "user": [{"user": "Administrator"}]}).insert(ignore_permissions=True)


class TestPlanTables(RolledBack):
	def test_the_plan_says_what_would_be_created_and_writes_nothing(self):
		before = (frappe.db.count("URY Room"), frappe.db.count("URY Table"))
		result = importer.plan_tables(places())
		self.assertEqual(result.errors, [])
		seen = verbs(result)
		self.assertEqual(seen[("URY Room", HALL)], "create")
		self.assertEqual(seen[("URY Room", PRIVATE)], "create")
		for name in (T1, T2, T_AWAY):
			self.assertEqual(seen[("URY Table", name)], "create")
		self.assertEqual((frappe.db.count("URY Room"), frappe.db.count("URY Table")), before)

	def test_a_room_that_belongs_to_another_branch_is_an_error(self):
		make_other_branch()
		frappe.get_doc(
			{"doctype": "URY Room", "name": HALL, "branch": OTHER_BRANCH}
		).insert(ignore_permissions=True)
		result = importer.plan_tables(places(rooms=[room(HALL)], tables=[table(T1)]))
		self.assertTrue(any(HALL in e and OTHER_BRANCH in e for e in result.errors), result.errors)

	def test_a_table_name_used_by_another_branch_is_an_error(self):
		make_other_branch()
		frappe.get_doc({"doctype": "URY Room", "name": PRIVATE, "branch": OTHER_BRANCH}).insert(ignore_permissions=True)
		frappe.get_doc(
			{"doctype": "URY Table", "name": T1, "restaurant": RESTAURANT, "branch": OTHER_BRANCH, "restaurant_room": PRIVATE}
		).insert(ignore_permissions=True)
		# the branch of a table is fetched from its restaurant when it is saved: make it another branch's table
		frappe.db.set_value("URY Table", T1, "branch", OTHER_BRANCH, update_modified=False)
		result = importer.plan_tables(places(rooms=[room(HALL)], tables=[table(T1)]))
		self.assertTrue(any(T1 in e and OTHER_BRANCH in e for e in result.errors), result.errors)

	def test_a_room_that_neither_the_sheet_nor_the_site_has_is_an_error(self):
		result = importer.plan_tables(places(rooms=[room(HALL)], tables=[table(T1, "どこにもない部屋")]))
		self.assertTrue(any("どこにもない部屋" in e for e in result.errors), result.errors)

	def test_the_shop_sheet_is_needed(self):
		data = places()
		data["shop"] = []
		result = importer.plan_tables(data)
		self.assertTrue(result.errors)

	def test_empty_sheets_change_nothing(self):
		result = importer.plan_tables(places(rooms=[], tables=[]))
		self.assertEqual(result.errors, [])
		self.assertEqual(result.changes, [])


class TestApplyTables(RolledBack):
	def test_it_creates_the_rooms_and_the_tables_with_the_names_of_the_sheet(self):
		result = importer.apply_tables(places())
		self.assertEqual(result.errors, [])
		self.assertEqual(frappe.db.get_value("URY Room", HALL, "branch"), BRANCH)
		t1 = frappe.db.get_value(
			"URY Table", T1, ["restaurant", "branch", "restaurant_room", "no_of_seats", "is_take_away", "table_shape", "occupied"],
			as_dict=True,
		)
		self.assertEqual(
			t1, {"restaurant": RESTAURANT, "branch": BRANCH, "restaurant_room": HALL, "no_of_seats": 4, "is_take_away": 0, "table_shape": "Square", "occupied": 0}
		)
		self.assertEqual(frappe.db.get_value("URY Table", T2, "restaurant_room"), PRIVATE)
		self.assertEqual(frappe.db.get_value("URY Table", T_AWAY, "is_take_away"), 1)
		self.assertFalse(frappe.db.get_value("URY Table", T_AWAY, "no_of_seats"))

	def test_importing_again_changes_nothing(self):
		importer.apply_tables(places())
		modified = frappe.db.get_value("URY Table", T1, "modified")
		again = importer.plan_tables(places())
		self.assertEqual(again.errors, [])
		self.assertEqual(again.changes, [])
		importer.apply_tables(places())
		self.assertEqual(frappe.db.get_value("URY Table", T1, "modified"), modified)

	def test_a_changed_sheet_updates_the_seats_the_room_and_the_take_away_mark_only(self):
		importer.apply_tables(places())
		frappe.db.set_value("URY Table", T1, {"occupied": 1, "self_order_open": 1, "self_order_opening": "abc"}, update_modified=False)
		changed = places(tables=[table(T1, PRIVATE, 8, True), table(T2, PRIVATE, 6), table(T_AWAY, HALL, None, True)])
		plan = importer.plan_tables(changed)
		self.assertEqual(verbs(plan)[("URY Table", T1)], "update")
		self.assertEqual(verbs(plan)[("URY Table", T2)], "same")
		importer.apply_tables(changed)
		values = frappe.db.get_value(
			"URY Table", T1, ["restaurant_room", "no_of_seats", "is_take_away", "occupied", "self_order_open", "self_order_opening"], as_dict=True
		)
		self.assertEqual(
			values, {"restaurant_room": PRIVATE, "no_of_seats": 8, "is_take_away": 1, "occupied": 1, "self_order_open": 1, "self_order_opening": "abc"}
		)

	def test_tables_and_rooms_of_the_site_that_the_sheets_do_not_list_are_kept_and_named(self):
		importer.apply_tables(places())
		result = importer.apply_tables(places(rooms=[room(HALL)], tables=[table(T1)]))
		self.assertIn(T2, result.extra)
		self.assertIn(PRIVATE, result.extra)
		self.assertTrue(frappe.db.exists("URY Table", T2))
		self.assertTrue(frappe.db.exists("URY Room", PRIVATE))

	def test_when_there_is_an_error_nothing_is_written(self):
		make_other_branch()
		frappe.get_doc({"doctype": "URY Room", "name": PRIVATE, "branch": OTHER_BRANCH}).insert(ignore_permissions=True)
		result = importer.apply_tables(places())
		self.assertTrue(result.errors)
		self.assertFalse(frappe.db.exists("URY Table", T1))
		self.assertFalse(frappe.db.exists("URY Room", HALL))

	def test_it_does_not_touch_the_menu_or_other_doctypes(self):
		counts = {d: frappe.db.count(d) for d in ("Item", "URY Menu", "URY Menu Course", "Item Price", "POS Invoice", "URY Production Unit")}
		importer.apply_tables(places())
		self.assertEqual({d: frappe.db.count(d) for d in counts}, counts)
