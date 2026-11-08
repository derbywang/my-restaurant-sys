"""The guards of the test site (test_guard.py): they must notice a changed role / account / permission and keep only
the newest automatic backups."""

import json
import os
import tempfile
import unittest
from unittest import mock

import frappe

from ury.setup import test_guard
from ury.setup.test_site import URYTestCase

PROBE_ROLE = "Guard Probe Role"
PROBE_USER = "guard-probe@test.local"


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
		self.assertIn("changed the roles, accounts or permissions", messages)
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
