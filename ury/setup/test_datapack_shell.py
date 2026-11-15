"""The shell of the data pack (docs/design/data-pack.md, step 6): the site settings, and plan / apply of the whole pack.

`plan_pack` reads and says what every step would do (all the errors at once); `apply_pack` takes the backup first, writes
the steps in an order that leaves nothing half done (the passwords are made last), and never goes on when the plan has an
error. The secret of the QR codes is given by the owner (a file only the owner can read, or typed); a new profile without
one is an error unless the owner says a new secret is meant. Everything runs in a rolled-back savepoint."""

import os
import stat
import tempfile
from unittest.mock import patch

import frappe
from frappe.utils.password import get_decrypted_password

from ury.setup.datapack import importer, ordering, shell
from ury.setup.test_datapack_menu import BEER, MENU, TUNA, RolledBack, pack
from ury.setup.test_datapack_ordering import KIOSK, PROFILE, SECRET, TABLET, make_device, make_profile, wipe
from ury.setup.test_datapack_staff import BOSS, HALL, person, rows
from ury.setup.test_datapack_tables import T1, T2, HALL as ROOM_HALL, PRIVATE, room, table

NEW_TABLE = "DP-新桌"
NEW_SECRET = "the-owners-secret-from-the-password-manager-9876"


def whole(**override):
	"""A pack with the menu, rooms, tables and staff of the other tests."""
	values = {
		"rooms": rows(room(ROOM_HALL), room(PRIVATE)),
		"tables": rows(table(T1), table(T2, PRIVATE, 6), table(NEW_TABLE)),
		"staff": rows(person(BOSS, "店長 太郎", "店長"), person(HALL, "ホール 次郎", "ホール", "zh")),
	}
	values.update(override)
	return pack(**values)


def ordering_file():
	"""What the rehearsal site gives: a profile whose tablet sits at a table the shop's site does not have yet."""
	make_profile()
	make_device(KIOSK, table=None, device_type="Kiosk", layout="Landscape Kiosk", table_mode="None", fixed_table=None)
	make_device(TABLET)
	data = ordering.export_ordering(PROFILE)
	wipe()
	for device in data["devices"]:
		if device["device_id"] == TABLET:
			device.update({"table_mode": "Fixed", "fixed_table": NEW_TABLE})
	return data


class TestSiteSettings(RolledBack):
	def setUp(self):
		super().setUp()
		frappe.db.set_single_value("System Settings", "language", "en")
		frappe.db.set_single_value("System Settings", "time_zone", "UTC")
		frappe.db.set_single_value("System Settings", "country", "India")
		frappe.db.set_single_value("System Settings", "login_with_email_link", 1)

	def test_the_plan_names_what_differs_and_writes_nothing(self):
		result = shell.plan_site_settings()
		self.assertEqual(result.errors, [])
		changed = {a.name for a in result.changes}
		self.assertEqual(changed, {"language", "time_zone", "country", "login_with_email_link"})
		self.assertEqual(frappe.db.get_single_value("System Settings", "language"), "en")

	def test_apply_sets_them_and_a_second_plan_is_empty(self):
		shell.apply_site_settings()
		self.assertEqual(frappe.db.get_single_value("System Settings", "language"), "ja")
		self.assertEqual(frappe.db.get_single_value("System Settings", "time_zone"), "Asia/Tokyo")
		self.assertEqual(frappe.db.get_single_value("System Settings", "country"), "Japan")
		self.assertEqual(frappe.db.get_single_value("Global Defaults", "default_currency"), "JPY")
		self.assertEqual(int(frappe.db.get_single_value("System Settings", "login_with_email_link")), 0)
		self.assertEqual(shell.plan_site_settings().changes, [])


class TestTheSecretOfTheCodes(RolledBack):
	def path(self, text, mode=0o600):
		path = os.path.join(tempfile.mkdtemp(), "secret.txt")
		descriptor = os.open(path, os.O_WRONLY | os.O_CREAT, mode)
		with os.fdopen(descriptor, "w") as handle:
			handle.write(text)
		os.chmod(path, mode)
		return path

	def test_the_value_of_the_file_without_the_line_break(self):
		self.assertEqual(shell.read_secret(self.path(NEW_SECRET + "\n")), NEW_SECRET)

	def test_a_file_others_can_read_is_refused(self):
		with self.assertRaises(shell.PackError) as caught:
			shell.read_secret(self.path(NEW_SECRET, 0o644))
		self.assertIn("600", str(caught.exception))

	def test_a_short_value_is_refused(self):
		with self.assertRaises(shell.PackError):
			shell.read_secret(self.path("short"))

	def test_a_file_that_is_not_there_is_refused(self):
		with self.assertRaises(shell.PackError):
			shell.read_secret("/nonexistent/secret.txt")

	def test_the_value_is_not_in_any_message(self):
		data = ordering_file()
		plan = shell.plan_pack(whole(), data, qr_secret=NEW_SECRET)
		self.assertNotIn(NEW_SECRET, shell.format_plan(plan))


class TestPlanPack(RolledBack):
	def test_every_step_is_planned_and_nothing_is_written(self):
		data = ordering_file()
		counts = {d: frappe.db.count(d) for d in ("URY Table", "User", "Item", "URY Self Ordering Profile", "URY Ordering Device")}
		plan = shell.plan_pack(whole(), data, qr_secret=NEW_SECRET)
		self.assertEqual(plan.all_errors, [])
		self.assertEqual([step.key for step in plan.steps], ["site", "menu", "tables", "ordering", "staff"])
		self.assertEqual({d: frappe.db.count(d) for d in counts}, counts)

	def test_the_tables_and_groups_the_pack_will_make_count_for_the_file_of_the_devices(self):
		data = ordering_file()
		plan = shell.plan_pack(whole(), data, qr_secret=NEW_SECRET)
		self.assertEqual(plan.all_errors, [])  # the tablet's table is made by the same pack
		plan = shell.plan_pack(whole(tables=rows(table(T1))), data, qr_secret=NEW_SECRET)
		self.assertTrue(any(NEW_TABLE in e for e in plan.all_errors), plan.all_errors)

	def test_the_errors_of_every_step_come_together(self):
		data = ordering_file()
		plan = shell.plan_pack(
			whole(tables=rows(table(T1, "どこにもない部屋")), staff=rows(person("not-an-email", "x", "店長"))), data, qr_secret=NEW_SECRET
		)
		self.assertTrue(any("どこにもない部屋" in e for e in plan.all_errors), plan.all_errors)
		self.assertGreaterEqual(len(plan.steps), 3)  # the other steps were planned too, not skipped after the first error

	def test_a_new_profile_without_a_secret_is_an_error_unless_a_new_one_is_meant(self):
		data = ordering_file()
		plan = shell.plan_pack(whole(), data)
		self.assertTrue(any("秘密鍵" in e for e in plan.all_errors), plan.all_errors)
		plan = shell.plan_pack(whole(), data, new_qr_secret=True)
		self.assertEqual(plan.all_errors, [])
		self.assertTrue(any("新しく" in n for n in plan.all_notes), plan.all_notes)

	def test_a_profile_that_is_there_needs_no_secret(self):
		data = ordering_file()
		make_profile()
		plan = shell.plan_pack(whole(), data)
		self.assertFalse(any("秘密鍵" in e for e in plan.all_errors), plan.all_errors)

	def test_without_the_file_of_the_devices_the_step_is_left_out(self):
		plan = shell.plan_pack(whole())
		self.assertEqual([step.key for step in plan.steps], ["site", "menu", "tables", "staff"])

	def test_the_text_says_what_each_step_does_and_what_the_pack_does_not_list(self):
		data = ordering_file()
		text = shell.format_plan(shell.plan_pack(whole(), data, qr_secret=NEW_SECRET))
		for word in (TUNA, T1, BOSS, PROFILE):
			self.assertIn(word, text)


class TestApplyPack(RolledBack):
	def apply(self, data=None, ordering_data=None, **kwargs):
		self.path = os.path.join(tempfile.mkdtemp(), "passwords.txt")
		self.backups = []
		kwargs.setdefault("backup", lambda: self.backups.append(True) or ["db.sql.gz", "site_config_backup.json"])
		return shell.apply_pack(
			data or whole(), ordering_data, password_file=kwargs.pop("password_file", self.path), **kwargs
		)

	def test_it_writes_every_step(self):
		data = ordering_file()
		plan = self.apply(whole(), data, qr_secret=NEW_SECRET)
		self.assertEqual(plan.all_errors, [])
		self.assertTrue(frappe.db.exists("Item", TUNA))
		self.assertTrue(frappe.db.exists("URY Table", NEW_TABLE))
		self.assertTrue(frappe.db.exists("User", BOSS))
		self.assertTrue(frappe.db.exists("URY Ordering Device", {"device_id": TABLET}))
		self.assertEqual(get_decrypted_password("URY Self Ordering Profile", PROFILE, "qr_signing_secret"), NEW_SECRET)
		self.assertEqual(frappe.db.get_single_value("System Settings", "language"), "ja")
		self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)

	def test_the_backup_is_taken_before_anything_is_written(self):
		seen = []

		def backup():
			seen.append((bool(frappe.db.exists("Item", TUNA)), bool(frappe.db.exists("User", BOSS))))
			return ["db.sql.gz"]

		self.apply(backup=backup)
		self.assertEqual(seen, [(False, False)])

	def test_the_files_of_the_backup_are_in_the_result(self):
		plan = self.apply()
		self.assertEqual(plan.backup, ["db.sql.gz", "site_config_backup.json"])

	def test_a_plan_with_an_error_takes_no_backup_and_writes_nothing(self):
		plan = self.apply(whole(tables=rows(table(T1, "どこにもない部屋"))))
		self.assertTrue(plan.all_errors)
		self.assertEqual(self.backups, [])
		self.assertFalse(frappe.db.exists("Item", TUNA))
		self.assertFalse(os.path.exists(self.path))

	def test_when_a_step_fails_no_password_file_is_left(self):
		with patch.object(importer, "apply_tables", side_effect=RuntimeError("boom")):
			with self.assertRaises(RuntimeError):
				self.apply()
		self.assertFalse(os.path.exists(self.path))

	def test_the_passwords_are_made_last(self):
		order = []
		for name in ("apply_menu", "apply_tables", "apply_staff"):
			original = getattr(importer, name)

			def wrapped(*args, _name=name, _original=original, **kwargs):
				order.append(_name)
				return _original(*args, **kwargs)

			patcher = patch.object(importer, name, wrapped)
			patcher.start()
			self.addCleanup(patcher.stop)
		self.apply()
		self.assertEqual(order, ["apply_menu", "apply_tables", "apply_staff"])

	def test_the_passwords_of_the_new_accounts_are_returned_and_in_the_file(self):
		plan = self.apply()
		self.assertEqual(set(plan.passwords), {BOSS, HALL})
		text = open(self.path, encoding="utf-8").read()
		for email, password in plan.passwords.items():
			self.assertIn(password, text)

	def test_applying_again_changes_nothing_and_makes_no_file(self):
		self.apply()
		again = self.apply()
		self.assertEqual(again.all_errors, [])
		self.assertEqual([a for step in again.steps for a in step.result.changes], [])
		self.assertEqual(again.passwords, {})
		self.assertFalse(os.path.exists(self.path))

	def test_the_profile_that_is_there_keeps_its_secret_when_the_same_one_is_given(self):
		data = ordering_file()
		make_profile(qr_signing_secret=NEW_SECRET)
		plan = self.apply(whole(), data, qr_secret=NEW_SECRET)
		self.assertEqual(plan.all_errors, [])
		other = self.apply(whole(), data, qr_secret=NEW_SECRET + "x")
		self.assertTrue(any("秘密鍵" in e for e in other.all_errors), other.all_errors)


class TestLoad(RolledBack):
	def test_a_file_that_is_not_there_is_an_error(self):
		data, ordering_data, errors = shell.load("/nonexistent/pack.xlsx")
		self.assertTrue(errors)

	def test_the_empty_template_is_read(self):
		from ury.setup.datapack.template import build_template

		path = os.path.join(tempfile.mkdtemp(), "pack.xlsx")
		build_template(path)
		data, ordering_data, errors = shell.load(path)
		self.assertEqual(errors, [])
		self.assertIsNone(ordering_data)


class TestCommand(RolledBack):
	"""`run_command`: what `bench --site <site> ury-datapack` does. The database calls that end a transaction are replaced."""

	def setUp(self):
		super().setUp()
		from ury.setup.datapack.template import build_template

		self.out = []
		self.dir = tempfile.mkdtemp()
		self.pack_path = os.path.join(self.dir, "pack.xlsx")
		build_template(self.pack_path)
		self.calls = []
		for name in ("commit", "rollback"):
			real = getattr(frappe.db, name)

			def fake(*args, _name=name, _real=real, **kwargs):
				if kwargs.get("save_point"):  # the test's own savepoint (setUp / tearDown) is real
					return _real(*args, **kwargs)
				self.calls.append(_name)

			patcher = patch.object(frappe.db, name, fake)
			patcher.start()
			self.addCleanup(patcher.stop)
		self.reads = lambda path: (whole(), None, [])
		patcher = patch.object(shell, "load", lambda path, ordering_path=None: self.reads(path))
		patcher.start()
		self.addCleanup(patcher.stop)

	def run_it(self, confirm=True, checks=None, **kwargs):
		kwargs.setdefault("password_file", os.path.join(self.dir, "passwords.txt"))
		return shell.run_command(
			self.pack_path,
			echo=self.out.append,
			confirm=lambda text: confirm,
			deploy_check=lambda: checks if checks is not None else [],
			backup=lambda: ["db.sql.gz", "site_config_backup.json"],
			**kwargs,
		)

	def test_without_apply_it_only_shows_the_plan(self):
		code = self.run_it()
		self.assertEqual(code, 0)
		self.assertFalse(frappe.db.exists("Item", TUNA))
		self.assertEqual(self.calls, [])
		self.assertIn(TUNA, "\n".join(self.out))

	def test_an_error_in_the_files_stops_with_a_failure_code(self):
		self.reads = lambda path: (None, None, ["シート「店舗」が見つかりません。"])
		self.assertEqual(self.run_it(apply=True, yes=True), 1)
		self.assertIn("シート「店舗」が見つかりません。", "\n".join(self.out))
		self.assertEqual(self.calls, [])

	def test_an_error_in_the_plan_writes_nothing(self):
		self.reads = lambda path: (whole(tables=rows(table(T1, "どこにもない部屋"))), None, [])
		self.assertEqual(self.run_it(apply=True, yes=True), 1)
		self.assertFalse(frappe.db.exists("Item", TUNA))
		self.assertEqual(self.calls, [])

	def test_when_the_owner_says_no_nothing_is_written(self):
		self.assertEqual(self.run_it(apply=True, confirm=False), 1)
		self.assertFalse(frappe.db.exists("Item", TUNA))
		self.assertEqual(self.calls, [])

	def test_it_applies_commits_once_and_runs_the_check(self):
		ran = []
		code = shell.run_command(
			self.pack_path, apply=True, yes=True, password_file=os.path.join(self.dir, "p.txt"), echo=self.out.append,
			deploy_check=lambda: ran.append(1) or [], backup=lambda: ["db.sql.gz", "site_config_backup.json"],
		)
		self.assertEqual(code, 0)
		self.assertTrue(frappe.db.exists("Item", TUNA))
		self.assertEqual(self.calls, ["commit"])
		self.assertEqual(ran, [1])
		text = "\n".join(self.out)
		self.assertIn("db.sql.gz", text)
		self.assertIn("p.txt", text)

	def test_the_passwords_are_not_printed(self):
		self.run_it(apply=True, yes=True)
		text = "\n".join(self.out)
		for password in open(os.path.join(self.dir, "passwords.txt"), encoding="utf-8").read().split():
			if len(password) == 14:
				self.assertNotIn(password, text)

	def test_a_failing_step_rolls_back_and_says_so(self):
		with patch.object(importer, "apply_tables", side_effect=shell.PackError("boom")):
			code = self.run_it(apply=True, yes=True)
		self.assertEqual(code, 1)
		self.assertEqual(self.calls, ["rollback"])
		self.assertIn("boom", "\n".join(self.out))
		self.assertFalse(os.path.exists(os.path.join(self.dir, "passwords.txt")))

	def test_a_fail_of_the_check_after_the_import_is_a_failure_code_but_the_import_stays(self):
		code = self.run_it(apply=True, yes=True, checks=[{"check": "x", "level": "FAIL", "detail": "d"}])
		self.assertEqual(code, 1)
		self.assertEqual(self.calls, ["commit"])

	def test_the_secret_of_the_file_is_used_and_not_printed(self):
		data = ordering_file()
		self.reads = lambda path: (whole(), data, [])
		path = os.path.join(self.dir, "secret.txt")
		descriptor = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
		with os.fdopen(descriptor, "w") as handle:
			handle.write(NEW_SECRET + "\n")
		code = self.run_it(apply=True, yes=True, ordering_path="x.json", qr_secret_file=path)
		self.assertEqual(code, 0, self.out)
		self.assertEqual(get_decrypted_password("URY Self Ordering Profile", PROFILE, "qr_signing_secret"), NEW_SECRET)
		self.assertNotIn(NEW_SECRET, "\n".join(self.out))

	def test_a_typed_secret_is_asked_for_only_when_wanted(self):
		data = ordering_file()
		self.reads = lambda path: (whole(), data, [])
		asked = []
		code = shell.run_command(
			self.pack_path, ordering_path="x.json", ask_qr_secret=True, echo=self.out.append, confirm=lambda t: True,
			prompt_secret=lambda: asked.append(1) or NEW_SECRET, deploy_check=lambda: [], apply=False,
		)
		self.assertEqual(code, 0, self.out)
		self.assertEqual(asked, [1])

	def test_a_bad_secret_file_is_a_failure_code_with_the_reason(self):
		self.assertEqual(self.run_it(qr_secret_file="/nonexistent/secret.txt", ordering_path="x.json"), 1)
		self.assertIn("/nonexistent/secret.txt", "\n".join(self.out))


class TestExportFile(RolledBack):
	def test_it_writes_the_file_for_the_owner_only_and_the_secret_is_not_in_it(self):
		make_profile()
		make_device()
		path = os.path.join(tempfile.mkdtemp(), "ordering.json")
		shell.export_file(PROFILE, path)
		self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
		text = open(path, encoding="utf-8").read()
		self.assertNotIn(SECRET, text)
		data, errors = ordering.read_export(path)
		self.assertEqual(errors, [])
		self.assertEqual({d["device_id"] for d in data["devices"]}, {TABLET})

	def test_a_profile_that_is_not_there_and_a_file_that_is_there_are_errors_for_the_owner(self):
		path = os.path.join(tempfile.mkdtemp(), "ordering.json")
		with self.assertRaises(shell.PackError):
			shell.export_file("そんな設定はない", path)
		make_profile()
		open(path, "w").close()
		with self.assertRaises(shell.PackError):
			shell.export_file(PROFILE, path)
