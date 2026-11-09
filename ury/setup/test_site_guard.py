"""The guards of the test site (test_guard.py): they must notice a changed role / account / permission and keep only
the newest automatic backups."""

import json
import os
import tempfile
import unittest
from unittest import mock

import frappe

from ury.setup import test_guard
from ury.setup.test_site import COMPANY, FOOD_ITEM, POS_PROFILE, URYTestCase

PROBE_ROLE = "Guard Probe Role"
PROBE_USER = "guard-probe@test.local"


class TestConfigSnapshot(URYTestCase):
	"""The shop's configuration (POS Profile, menu, kitchens, payment accounts, settings ...) is guarded like the roles:
	a changed value, an added row or a removed row is reported with the table and the field."""

	def _diff(self, change):
		before = test_guard.access_snapshot()
		change()
		lines = test_guard.access_diff(before, test_guard.access_snapshot())
		frappe.db.rollback()
		return lines

	def test_nothing_changed_nothing_reported(self):
		self.assertEqual(self._diff(lambda: None), [])

	def test_a_changed_value_of_a_pos_profile_is_named(self):
		lines = self._diff(lambda: frappe.db.set_value("POS Profile", POS_PROFILE, "customer", "somebody else"))
		self.assertTrue(any("POS Profile" in l and POS_PROFILE in l and "customer" in l for l in lines), lines)

	def test_a_change_that_keeps_the_modified_time_is_found_too(self):
		lines = self._diff(
			lambda: frappe.db.set_value("POS Profile", POS_PROFILE, "customer", "somebody else", update_modified=False)
		)
		self.assertTrue(any("customer" in l for l in lines), lines)

	def test_a_new_and_a_removed_row(self):
		def change():
			frappe.get_doc({"doctype": "Price List", "price_list_name": "guard-test-list", "currency": "JPY", "selling": 1}).insert()
			frappe.db.delete("URY Menu Item", {"item": FOOD_ITEM})

		lines = self._diff(change)
		self.assertTrue(any("Price List" in l and "guard-test-list" in l and "added" in l for l in lines), lines)
		self.assertTrue(any("URY Menu Item" in l and FOOD_ITEM in l and "removed" in l for l in lines), lines)

	def test_a_child_row_written_again_with_a_new_name_is_not_a_change(self):
		def rewrite():
			row = frappe.db.get_value("URY Production Item Groups", {}, "name")
			frappe.db.set_value("URY Production Item Groups", row, "name", "renamed-row-for-the-guard", update_modified=False)

		self.assertEqual(self._diff(rewrite), [])

	def test_a_child_row_that_is_added_is_a_change(self):
		def add():
			frappe.get_doc(
				{"doctype": "URY User", "parent": "テスト店", "parenttype": "Branch", "parentfield": "user", "user": "x-guard@test.local"}
			).db_insert()

		self.assertTrue(any("URY User" in l and "x-guard@test.local" in l and "added" in l for l in self._diff(add)))

	def test_what_every_order_changes_is_not_reported(self):
		lines = self._diff(lambda: frappe.db.set_value("Company", COMPANY, "total_monthly_sales", 123456))
		self.assertEqual(lines, [])

	def test_the_time_stamp_of_a_setting_is_not_reported(self):
		lines = self._diff(lambda: frappe.db.sql("update tabSingles set value = '2000-01-01' where doctype = 'System Settings' and field = 'modified'"))
		self.assertEqual(lines, [])

	def test_each_group_of_configuration_is_watched(self):
		watched = set(test_guard.CONFIG_DOCTYPES) | set(test_guard.CONFIG_SINGLES)
		for doctype in (
			"POS Profile", "URY Self Ordering Profile", "URY Restaurant", "Branch", "Company", "Mode of Payment Account",
			"URY Menu", "URY Menu Item", "URY Production Unit", "Print Format", "Scheduled Job Type",
			"System Settings", "Global Defaults", "Selling Settings",
		):
			self.assertIn(doctype, watched, doctype)

	def test_a_custom_field_is_watched(self):
		lines = self._diff(lambda: frappe.db.set_value("Custom Field", "POS Invoice-restaurant_table", "read_only", 1 - (frappe.db.get_value("Custom Field", "POS Invoice-restaurant_table", "read_only") or 0)))
		self.assertTrue(any("Custom Field" in l and "read_only" in l for l in lines), lines)

	def test_a_single_setting_is_watched(self):
		old = frappe.db.get_single_value("System Settings", "language")
		lines = self._diff(lambda: frappe.db.set_single_value("System Settings", "language", "xx" if old != "xx" else "en"))
		self.assertTrue(any("System Settings" in l and "language" in l for l in lines), lines)

	def test_what_a_test_changes_all_the_time_is_not_reported(self):
		# the table's own working state (taken, since when) is the tests' daily business
		table = frappe.db.get_value("URY Table", {}, "name")
		lines = self._diff(lambda: frappe.db.set_value("URY Table", table, {"occupied": 1, "self_order_open": 1}))
		self.assertEqual(lines, [])

	def test_the_check_names_the_table_and_points_to_the_backup(self):
		before = test_guard.access_snapshot()
		frappe.db.set_value("POS Profile", POS_PROFILE, "customer", "somebody else")
		try:
			with self.assertRaises(AssertionError) as caught:
				test_guard.check_unchanged("SomeTests", before)
		finally:
			frappe.db.rollback()
		self.assertIn("POS Profile", str(caught.exception))
		self.assertIn("backup", str(caught.exception))


class TestAccessSnapshot(URYTestCase):
	def _diff(self, change):
		before = test_guard.access_snapshot()
		change()
		return test_guard.access_diff(before, test_guard.access_snapshot())

	def test_nothing_changed_nothing_reported(self):
		self.assertEqual(self._diff(lambda: None), [])

	def test_a_role_that_lost_its_desk(self):
		old = frappe.db.get_value("Role", "URY Cashier", "desk_access")
		lines = self._diff(lambda: frappe.db.set_value("Role", "URY Cashier", "desk_access", 1 - old))
		self.assertEqual(lines, [f"Role URY Cashier: {{'desk_access': ({old}, {1 - old})}}"])
		frappe.db.rollback()

	def test_a_new_role_and_a_removed_one(self):
		lines = self._diff(lambda: frappe.get_doc({"doctype": "Role", "role_name": PROBE_ROLE}).insert())
		self.assertTrue(any(PROBE_ROLE in line and "added" in line for line in lines))
		frappe.db.rollback()

	def test_a_new_account_and_its_role(self):
		def add():
			frappe.get_doc({"doctype": "User", "email": PROBE_USER, "first_name": "Probe", "send_welcome_email": 0,
				"roles": [{"role": "URY Cashier"}]}).insert(ignore_permissions=True)

		lines = self._diff(add)
		self.assertTrue(any(line.startswith(f"User {PROBE_USER}: added") for line in lines))
		self.assertTrue(any("Has Role (users)" in line and PROBE_USER in line for line in lines))
		frappe.db.rollback()

	def test_a_changed_account(self):
		lines = self._diff(lambda: frappe.db.set_value("User", "cashier@test.local", "enabled", 0))
		self.assertEqual(lines, ["User cashier@test.local: {'enabled': (1, 0)}"])
		frappe.db.rollback()

	def test_a_changed_permission(self):
		row = frappe.db.get_value("Custom DocPerm", {"role": "URY Cashier"}, "name")
		if not row:
			self.skipTest("no Custom DocPerm of URY Cashier on this site")
		old = frappe.db.get_value("Custom DocPerm", row, "export")
		lines = self._diff(lambda: frappe.db.set_value("Custom DocPerm", row, "export", 0 if old else 1))
		self.assertTrue(any(line.startswith("Custom DocPerm: ") for line in lines), lines)
		frappe.db.rollback()

	def test_timestamps_and_logins_do_not_count(self):
		def touch():
			frappe.db.set_value("User", "cashier@test.local", {"last_login": "2026-01-01 00:00:00", "last_active": "2026-01-01 00:00:00"})
			frappe.db.set_value("Role", "URY Cashier", "modified", "2026-01-01 00:00:00", update_modified=False)

		self.assertEqual(self._diff(touch), [])
		frappe.db.rollback()

	def test_the_check_names_the_class_and_lists_the_difference(self):
		before = test_guard.access_snapshot()
		frappe.db.set_value("Role", "URY Cashier", "desk_access", 1 - frappe.db.get_value("Role", "URY Cashier", "desk_access"))
		with self.assertRaises(AssertionError) as caught:
			test_guard.check_unchanged("SomeTests", before)
		frappe.db.rollback()
		self.assertIn("SomeTests", str(caught.exception))
		self.assertIn("URY Cashier", str(caught.exception))
		self.assertIn("desk_access", str(caught.exception))


class TestAClassThatLeaksFails(URYTestCase):
	"""The real thing: a test class that commits a new role is reported as an error by the guard of URYTestCase."""

	def test_a_leaking_class_is_an_error(self):
		class Leaky(URYTestCase):
			def test_leak(self):
				frappe.get_doc({"doctype": "Role", "role_name": PROBE_ROLE}).insert()
				frappe.db.commit()

		self.addCleanup(self._remove_probe)
		result = unittest.TextTestRunner(stream=open(os.devnull, "w")).run(unittest.defaultTestLoader.loadTestsFromTestCase(Leaky))
		messages = " ".join(text for _case, text in result.errors + result.failures)
		self.assertIn("changed the roles, accounts, permissions or configuration", messages)
		self.assertIn(PROBE_ROLE, messages)

	def _remove_probe(self):
		if frappe.db.exists("Role", PROBE_ROLE):
			frappe.delete_doc("Role", PROBE_ROLE, force=True, ignore_permissions=True)
		frappe.db.commit()


class TestAutomaticBackups(URYTestCase):
	def _run(self, folder, made):
		def fake_backup(**_kwargs):
			for name in made:
				open(os.path.join(folder, name), "w").close()

		with mock.patch.object(test_guard, "_backup_dir", return_value=folder), mock.patch.object(test_guard, "_checked_backup", False), mock.patch(
			"frappe.utils.backups.new_backup", side_effect=fake_backup
		):
			test_guard.ensure_recent_backup()

	def test_only_the_newest_ten_automatic_backups_stay_and_manual_ones_are_never_deleted(self):
		with tempfile.TemporaryDirectory() as folder:
			old = [f"2026110{i}_000000-site" for i in range(1, 10)] + [f"2026111{i}_000000-site" for i in range(0, 4)]  # 13
			for prefix in old:
				for suffix in ("-database.sql.gz", "-site_config_backup.json"):
					open(os.path.join(folder, prefix + suffix), "w").close()
			manual = "20261101_999999-site-database.sql.gz"
			open(os.path.join(folder, manual), "w").close()
			json.dump(old, open(os.path.join(folder, test_guard.MANIFEST), "w"))
			for name in os.listdir(folder):
				os.utime(os.path.join(folder, name), (1, 1))  # all old: a new backup is due

			self._run(folder, ["20261120_000000-site-database.sql.gz", "20261120_000000-site-site_config_backup.json"])

			listed = json.load(open(os.path.join(folder, test_guard.MANIFEST)))
			self.assertEqual(len(listed), test_guard.KEEP_AUTO_BACKUPS)
			self.assertEqual(listed[-1], "20261120_000000-site")
			files = set(os.listdir(folder))
			self.assertIn(manual, files)
			self.assertIn("20261120_000000-site-database.sql.gz", files)
			self.assertNotIn(f"{old[0]}-database.sql.gz", files)
			self.assertNotIn(f"{old[0]}-site_config_backup.json", files)
			self.assertIn(f"{old[-1]}-database.sql.gz", files)
			self.assertEqual(len([f for f in files if f.endswith("-database.sql.gz") and f != manual]), test_guard.KEEP_AUTO_BACKUPS)

	def test_a_recent_backup_means_no_new_one(self):
		with tempfile.TemporaryDirectory() as folder:
			open(os.path.join(folder, "20260101_000000-site-database.sql.gz"), "w").close()  # just written
			self._run(folder, ["20261120_000000-site-database.sql.gz"])
			self.assertEqual(os.listdir(folder), ["20260101_000000-site-database.sql.gz"])

	def test_an_old_backup_means_a_new_one(self):
		with tempfile.TemporaryDirectory() as folder:
			old = os.path.join(folder, "20260101_000000-site-database.sql.gz")
			open(old, "w").close()
			os.utime(old, (1, 1))
			self._run(folder, ["20261120_000000-site-database.sql.gz"])
			self.assertIn("20261120_000000-site-database.sql.gz", os.listdir(folder))
