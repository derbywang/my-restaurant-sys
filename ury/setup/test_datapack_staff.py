"""The data pack imports the staff accounts (docs/design/data-pack.md, step 4).

The sheet has the name, the login id, the role and the language; it has no password. `apply_staff` makes an initial
password for each NEW account (random, one for each person) and writes them to a file only the owner can read; an account
that exists keeps its password. Everything runs in a rolled-back savepoint of the test site."""

import os
import stat
import tempfile
from unittest.mock import patch

import frappe
from frappe.utils.password import check_password

from ury.setup.datapack import importer
from ury.setup.datapack.reader import Row
from ury.setup.test_datapack_menu import RolledBack, pack
from ury.setup.test_site import BRANCH, POS_PROFILE

HALL = "dp-hall@example.com"
CASH = "dp-cash@example.com"
KITCHEN = "dp-kitchen@example.com"
BOSS = "dp-boss@example.com"


def person(email, name, role, language=None):
	return {"name": name, "email": email, "role": role, "language": language, "note": None}


def rows(*values):
	return [Row(5 + i, v) for i, v in enumerate(values)]


def staff(*people):
	return pack(
		staff=rows(
			*(
				people
				or (
					person(BOSS, "店長 太郎", "店長"),
					person(CASH, "レジ 花子", "レジ担当", "ja"),
					person(HALL, "ホール 次郎", "ホール", "zh"),
					person(KITCHEN, "厨房 三郎", "厨房", "en"),
				)
			)
		)
	)


def roles_of(user):
	return set(frappe.get_all("Has Role", filters={"parenttype": "User", "parent": user, "role": ("like", "URY %")}, pluck="role"))


def in_branch(user):
	return bool(frappe.db.exists("URY User", {"parenttype": "Branch", "parent": BRANCH, "user": user}))


def in_profile(user):
	return bool(frappe.db.exists("POS Profile User", {"parent": POS_PROFILE, "user": user}))


def logs_in(user, password):
	try:
		check_password(user, password)
		return True
	except frappe.AuthenticationError:
		return False


class TestPlanStaff(RolledBack):
	def test_the_plan_says_what_would_be_created_and_writes_nothing(self):
		users = frappe.db.count("User")
		result = importer.plan_staff(staff())
		self.assertEqual(result.errors, [])
		seen = {(a.doctype, a.name): a.verb for a in result.actions}
		for email in (BOSS, CASH, HALL, KITCHEN):
			self.assertEqual(seen[("User", email)], "create")
		self.assertEqual(frappe.db.count("User"), users)
		self.assertFalse(in_branch(HALL))
		self.assertEqual(result.passwords, {})

	def test_an_account_with_another_role_than_the_sheet_says_is_an_error(self):
		frappe.get_doc(
			{"doctype": "User", "email": HALL, "first_name": "x", "send_welcome_email": 0, "roles": [{"role": "URY Cashier"}]}
		).insert(ignore_permissions=True)
		result = importer.plan_staff(staff(person(HALL, "ホール 次郎", "ホール")))
		self.assertTrue(any(HALL in e and "URY Cashier" in e for e in result.errors), result.errors)

	def test_a_disabled_account_is_an_error_not_switched_on(self):
		frappe.get_doc(
			{"doctype": "User", "email": HALL, "first_name": "x", "send_welcome_email": 0, "enabled": 0, "roles": [{"role": "URY Captain"}]}
		).insert(ignore_permissions=True)
		result = importer.plan_staff(staff(person(HALL, "ホール 次郎", "ホール")))
		self.assertTrue(any(HALL in e for e in result.errors), result.errors)

	def test_the_shop_sheet_is_needed(self):
		data = staff()
		data["shop"] = []
		self.assertTrue(importer.plan_staff(data).errors)


class TestApplyStaff(RolledBack):
	def apply(self, data=None, **kwargs):
		self.path = os.path.join(tempfile.mkdtemp(), "passwords.txt")
		return importer.apply_staff(data or staff(), password_file=kwargs.pop("password_file", self.path), **kwargs)

	def test_it_makes_the_accounts_with_the_role_the_language_and_the_places(self):
		result = self.apply()
		self.assertEqual(result.errors, [])
		self.assertEqual(roles_of(BOSS), {"URY Manager"})
		self.assertEqual(roles_of(CASH), {"URY Cashier"})
		self.assertEqual(roles_of(HALL), {"URY Captain"})
		self.assertEqual(roles_of(KITCHEN), {"URY Kitchen"})
		values = frappe.db.get_value("User", HALL, ["first_name", "language", "enabled", "send_welcome_email", "user_type"], as_dict=True)
		self.assertEqual(
			values, {"first_name": "ホール 次郎", "language": "zh", "enabled": 1, "send_welcome_email": 0, "user_type": "Website User"}
		)
		self.assertEqual(frappe.db.get_value("User", BOSS, "language"), "ja")  # an empty cell is ja
		# every account is in the branch (the kitchen's push and the staff check need it); the profile lets the people who
		# take orders or the money in, not the kitchen screen
		for email in (BOSS, CASH, HALL, KITCHEN):
			self.assertTrue(in_branch(email), email)
		for email in (BOSS, CASH, HALL):
			self.assertTrue(in_profile(email), email)
		self.assertFalse(in_profile(KITCHEN))

	def test_each_new_account_gets_its_own_password_and_it_logs_in(self):
		result = self.apply()
		self.assertEqual(set(result.passwords), {BOSS, CASH, HALL, KITCHEN})
		self.assertEqual(len(set(result.passwords.values())), 4)
		for email, password in result.passwords.items():
			self.assertGreaterEqual(len(password), 12)
			self.assertTrue(logs_in(email, password), email)
			self.assertFalse(logs_in(email, password + "x"))

	def test_the_passwords_are_in_a_file_only_the_owner_can_read(self):
		result = self.apply()
		self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)
		text = open(self.path, encoding="utf-8").read()
		for email, password in result.passwords.items():
			self.assertIn(email, text)
			self.assertIn(password, text)

	def test_a_file_that_is_there_is_never_overwritten(self):
		path = os.path.join(tempfile.mkdtemp(), "passwords.txt")
		with open(path, "w") as handle:
			handle.write("old")
		result = importer.apply_staff(staff(), password_file=path)
		self.assertTrue(result.errors)
		self.assertEqual(open(path).read(), "old")
		self.assertFalse(frappe.db.exists("User", HALL))

	def test_when_making_an_account_fails_nothing_is_left_not_even_the_file(self):
		path = os.path.join(tempfile.mkdtemp(), "passwords.txt")
		original = importer._StaffImport._create_user
		calls = []

		def failing(self, person):
			calls.append(person["email"])
			if len(calls) == 2:
				raise RuntimeError("boom")
			return original(self, person)

		with patch.object(importer._StaffImport, "_create_user", failing):
			with self.assertRaises(RuntimeError):
				importer.apply_staff(staff(), password_file=path)
		self.assertFalse(os.path.exists(path))

	def test_importing_again_changes_nothing_and_makes_no_file(self):
		self.apply()
		again = self.apply()
		self.assertEqual(again.errors, [])
		self.assertEqual(again.changes, [])
		self.assertEqual(again.passwords, {})
		self.assertFalse(os.path.exists(self.path))

	def test_an_account_that_is_there_keeps_its_password_and_is_put_in_its_places(self):
		frappe.get_doc(
			{
				"doctype": "User", "email": CASH, "first_name": "Old", "send_welcome_email": 0, "language": "en",
				"roles": [{"role": "URY Cashier"}],
			}
		).insert(ignore_permissions=True)
		from frappe.utils.password import update_password

		update_password(CASH, "Kept-Password-2026!")
		result = self.apply(staff(person(CASH, "レジ 花子", "レジ担当", "ja")))
		self.assertEqual(result.passwords, {})
		self.assertTrue(logs_in(CASH, "Kept-Password-2026!"))
		self.assertTrue(in_branch(CASH))
		self.assertTrue(in_profile(CASH))
		self.assertEqual(frappe.db.get_value("User", CASH, "language"), "ja")
		self.assertFalse(os.path.exists(self.path))

	def test_accounts_of_the_site_that_the_sheet_does_not_list_are_kept_and_named(self):
		result = self.apply()
		self.assertIn("cashier@test.local", result.extra)
		self.assertTrue(frappe.db.exists("User", "cashier@test.local"))

	def test_when_there_is_an_error_nothing_is_written(self):
		frappe.get_doc(
			{"doctype": "User", "email": HALL, "first_name": "x", "send_welcome_email": 0, "roles": [{"role": "URY Cashier"}]}
		).insert(ignore_permissions=True)
		result = self.apply()
		self.assertTrue(result.errors)
		self.assertFalse(frappe.db.exists("User", BOSS))
		self.assertFalse(os.path.exists(self.path))
