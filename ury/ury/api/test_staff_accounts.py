"""The manager makes the accounts of the staff of the shop (ury/ury/api/staff_accounts.py).

The manager has no right to write a User (the tightening of 2026-11-08: only a System Manager decides who gets which role). What the
manager may do is this one narrow call: make an account of the three staff roles (cashier, waiter, kitchen), in the manager's own
branch, with a random password that is shown once. Nothing else: no manager, no URY Admin, no System Manager, no change of an account
that exists. Test site only.
"""

import re
from unittest.mock import patch

import frappe
from frappe.utils import add_to_date, now_datetime

from ury.ury.api import staff_accounts
from ury.ury.api.test_captain_access import OTHER_BRANCH, make_captain, remove_captain
from ury.setup.test_site import BRANCH, CAPTAIN, CASHIER, MANAGER, POS_PROFILE, URYTestCase, as_user

NEW = "new-staff@test.local"
OTHER_MANAGER = "second-branch-manager@test.local"
ADMIN = "admin@test.local"
PASSWORD_SHAPE = re.compile(r"^[A-Za-z0-9]{14}$")


def make(first_name="新人", login_id=NEW, role="URY Cashier", **kwargs):
	return staff_accounts.create_staff_account(first_name=first_name, login_id=login_id, role=role, **kwargs)


class StaffAccountCase(URYTestCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(self.clean_up)
		self.clean_up()

	def clean_up(self):
		for email in (NEW, "second@test.local"):
			for parent in frappe.get_all("URY User", filters={"user": email, "parenttype": "Branch"}, pluck="parent"):
				branch = frappe.get_doc("Branch", parent)
				branch.user = [row for row in branch.user if row.user != email]
				if not branch.user and parent == OTHER_BRANCH:  # the branch the tests made for the other side: nobody left, it goes
					frappe.delete_doc("Branch", parent, force=True, ignore_permissions=True)
				else:
					branch.save(ignore_permissions=True)
			for row in frappe.get_all("POS Profile User", filters={"user": email}, pluck="name"):
				frappe.delete_doc("POS Profile User", row, force=True, ignore_permissions=True)
			frappe.db.delete("Activity Log", {"reference_doctype": "User", "reference_name": email})
			if frappe.db.exists("User", email):
				frappe.delete_doc("User", email, force=True, ignore_permissions=True)
		remove_captain(OTHER_MANAGER)
		frappe.db.commit()

	def roles_of(self, email):
		return sorted(frappe.get_all("Has Role", filters={"parenttype": "User", "parent": email}, pluck="role"))


class TestTheManagerMakesAnAccount(StaffAccountCase):
	def test_a_cashier_account_is_made_in_the_managers_branch(self):
		with as_user(MANAGER):
			answer = make()
		self.assertEqual((answer["login_id"], answer["role"], answer["branch"]), (NEW, "URY Cashier", BRANCH))
		user = frappe.get_doc("User", NEW)
		self.assertEqual(self.roles_of(NEW), ["URY Cashier"])
		self.assertEqual((user.enabled, user.first_name, user.language), (1, "新人", "ja"))
		self.assertTrue(frappe.db.exists("URY User", {"parenttype": "Branch", "parent": BRANCH, "user": NEW}))
		self.assertTrue(frappe.db.exists("POS Profile User", {"parent": POS_PROFILE, "user": NEW}))

	def test_a_waiter_account_is_made_the_same_way(self):
		with as_user(MANAGER):
			make(role="URY Captain")
		self.assertEqual(self.roles_of(NEW), ["URY Captain"])
		self.assertTrue(frappe.db.exists("POS Profile User", {"parent": POS_PROFILE, "user": NEW}))

	def test_a_kitchen_account_is_in_the_branch_but_not_on_the_register(self):
		with as_user(MANAGER):
			make(role="URY Kitchen")
		self.assertEqual(self.roles_of(NEW), ["URY Kitchen"])
		self.assertTrue(frappe.db.exists("URY User", {"parenttype": "Branch", "parent": BRANCH, "user": NEW}))
		self.assertFalse(frappe.db.exists("POS Profile User", {"parent": POS_PROFILE, "user": NEW}))

	def test_the_new_account_can_log_in_with_the_password_shown(self):
		from frappe.utils.password import check_password

		with as_user(MANAGER):
			answer = make()
		self.assertRegex(answer["initial_password"], PASSWORD_SHAPE)
		self.assertEqual(check_password(NEW, answer["initial_password"]), NEW)

	def test_the_password_is_random_each_time(self):
		with as_user(MANAGER):
			first = make()["initial_password"]
		self.clean_up()
		with as_user(MANAGER):
			second = make()["initial_password"]
		self.assertNotEqual(first, second)

	def test_the_password_is_shown_once_and_is_nowhere_to_be_read_again(self):
		errors = frappe.db.count("Error Log")
		queued = frappe.db.count("Email Queue")
		with as_user(MANAGER):
			answer = make()
		password = answer["initial_password"]
		self.assertEqual(set(answer), {"login_id", "full_name", "role", "branch", "initial_password"})
		for table, fields in (("Activity Log", ["subject", "content"]), ("Version", ["data"]), ("Comment", ["content"]), ("Error Log", ["error"])):
			for row in frappe.get_all(table, fields=fields, limit_page_length=0):
				self.assertNotIn(password, " ".join(str(v) for v in row.values()), table)
		self.assertEqual(frappe.db.count("Error Log"), errors)
		self.assertEqual(frappe.db.count("Email Queue"), queued)  # no mail: not a welcome mail, not a password mail

	def test_every_account_made_is_in_the_operation_log_with_who_what_role_and_when(self):
		before = now_datetime()
		with as_user(MANAGER):
			make(role="URY Captain")
		row = frappe.get_all("Activity Log", filters={"reference_doctype": "User", "reference_name": NEW}, fields=["subject", "user", "communication_date"])
		self.assertEqual(len(row), 1)
		self.assertEqual(row[0].user, MANAGER)
		for part in (MANAGER, NEW, "URY Captain", BRANCH):
			self.assertIn(part, row[0].subject)
		self.assertGreaterEqual(row[0].communication_date, add_to_date(before, seconds=-5))

	def test_the_managers_right_to_write_a_user_is_not_widened(self):
		self.assertFalse(frappe.has_permission("User", "create", user=MANAGER))
		with as_user(MANAGER):
			make()
		self.assertFalse(frappe.has_permission("User", "create", user=MANAGER))
		self.assertFalse(frappe.has_permission("User", "write", doc=CASHIER, user=MANAGER))  # (everyone may write their own profile)
		self.assertFalse(frappe.has_permission("User", "write", doc=NEW, user=MANAGER))

	def test_the_page_is_told_what_the_manager_may_do(self):
		with as_user(MANAGER):
			options = staff_accounts.get_staff_account_options()
		self.assertTrue(options["can_create"])
		self.assertEqual(options["roles"], ["URY Cashier", "URY Captain", "URY Kitchen"])
		self.assertEqual(options["branches"], [BRANCH])
		with as_user(CASHIER):
			self.assertFalse(staff_accounts.get_staff_account_options()["can_create"])


class TestWhatIsRefused(StaffAccountCase):
	def refused(self, user, exc=(frappe.PermissionError, frappe.ValidationError), **kwargs):
		"""The call is refused and changes nothing: the user, the rows in a branch and the log are as they were."""
		login = kwargs.get("login_id", NEW)
		existed = frappe.db.exists("User", login)
		logs = frappe.db.count("Activity Log", {"reference_name": login})
		rows = frappe.db.count("URY User", {"parenttype": "Branch", "user": login})
		with as_user(user):
			with self.assertRaises(exc):
				make(**kwargs)
		self.assertEqual(bool(frappe.db.exists("User", login)), bool(existed))
		self.assertEqual(frappe.db.count("Activity Log", {"reference_name": login}), logs)
		self.assertEqual(frappe.db.count("URY User", {"parenttype": "Branch", "user": login}), rows)

	def test_nobody_but_a_manager_may_call_it(self):
		for user in (CASHIER, CAPTAIN, "Guest"):
			self.refused(user, exc=frappe.PermissionError)
		self.assertFalse(frappe.db.exists("User", NEW))

	def test_a_manager_cannot_be_made(self):
		self.refused(MANAGER, role="URY Manager")

	def test_the_roles_that_rule_the_system_cannot_be_made(self):
		for role in ("URY Admin", "System Manager", "Administrator", "Desk User", "All", "Guest"):
			self.refused(MANAGER, role=role)
			self.assertFalse(frappe.db.exists("User", NEW), role)

	def test_two_roles_in_one_value_or_no_role_are_refused(self):
		for role in ("URY Cashier,System Manager", "URY Cashier\nSystem Manager", "", "ury cashier", "URY Cashier "):
			self.refused(MANAGER, role=role)

	def test_another_branch_is_refused(self):
		make_captain("someone-else@test.local", branch=OTHER_BRANCH)
		self.addCleanup(remove_captain, "someone-else@test.local")
		self.refused(MANAGER, exc=frappe.PermissionError, branch=OTHER_BRANCH)

	def test_a_manager_of_two_branches_must_say_which(self):
		make_captain("someone-else@test.local", branch=OTHER_BRANCH)
		self.addCleanup(remove_captain, "someone-else@test.local")
		other = frappe.get_doc("Branch", OTHER_BRANCH)
		other.append("user", {"user": MANAGER})
		other.save(ignore_permissions=True)

		def undo():
			branch = frappe.get_doc("Branch", OTHER_BRANCH)
			branch.user = [row for row in branch.user if row.user != MANAGER]
			branch.save(ignore_permissions=True)

		self.addCleanup(undo)
		self.refused(MANAGER, exc=frappe.ValidationError)
		with as_user(MANAGER):
			answer = make(branch=BRANCH)
		self.assertEqual(answer["branch"], BRANCH)
		self.assertFalse(frappe.db.exists("URY User", {"parenttype": "Branch", "parent": OTHER_BRANCH, "user": NEW}))

	def test_an_account_that_exists_is_never_touched(self):
		roles = self.roles_of(ADMIN)
		for login in (ADMIN, ADMIN.upper(), CASHIER, MANAGER):
			self.refused(MANAGER, login_id=login)
		self.assertEqual(self.roles_of(ADMIN), roles)
		self.assertIn("System Manager", roles)

	def test_a_second_account_with_the_same_login_is_refused(self):
		with as_user(MANAGER):
			make()
		self.refused(MANAGER, exc=frappe.ValidationError, first_name="別人")
		self.assertEqual(frappe.db.get_value("User", NEW, "first_name"), "新人")

	def test_a_login_id_must_look_like_one(self):
		for login in ("", "no-at-sign", "has space@test.local", "@test.local", "x@", "a@b@c.local"):
			self.refused(MANAGER, exc=frappe.ValidationError, login_id=login)

	def test_a_name_is_needed_and_is_not_too_long(self):
		for name in ("", "   ", "あ" * 141):
			self.refused(MANAGER, exc=frappe.ValidationError, first_name=name)

	def test_when_the_password_cannot_be_set_nothing_is_left_and_the_password_is_not_in_a_log(self):
		errors = frappe.db.count("Error Log")
		with as_user(MANAGER):
			with patch("frappe.utils.password.update_password", side_effect=RuntimeError("boom")):
				with self.assertRaises(frappe.ValidationError):
					make()
		self.assertFalse(frappe.db.exists("User", NEW))
		self.assertFalse(frappe.db.exists("URY User", {"parenttype": "Branch", "user": NEW}))
		self.assertEqual(frappe.get_all("Activity Log", filters={"reference_name": NEW}), [])
		self.assertEqual(frappe.db.count("Error Log"), errors)


class TestAFailureNeverTakesAnAccountThatWasThere(StaffAccountCase):
	"""Found by breaking the duplicate check on purpose (2026-11-18): the old clean-up deleted the account of that login, which was
	somebody else's. Only an account this test made is used here."""

	def test_when_the_guard_is_beaten_to_it_the_account_that_was_there_stays(self):
		with as_user(MANAGER):
			make(role="URY Captain")
		roles = self.roles_of(NEW)
		rows = frappe.db.count("URY User", {"parenttype": "Branch", "user": NEW})
		with patch.object(staff_accounts.frappe.db, "exists", return_value=None):  # as if two calls came at the same moment
			with as_user(MANAGER):
				with self.assertRaises(frappe.ValidationError):
					make(first_name="別人")
		self.assertTrue(frappe.db.exists("User", NEW))
		self.assertEqual(frappe.db.get_value("User", NEW, "first_name"), "新人")
		self.assertEqual(self.roles_of(NEW), roles)
		self.assertEqual(frappe.db.count("URY User", {"parenttype": "Branch", "user": NEW}), rows)
		self.assertEqual(frappe.db.count("Activity Log", {"reference_name": NEW}), 1)


class TestItIsOnTheWhitelistAsAPost(URYTestCase):
	def test_making_an_account_is_a_post_and_looking_is_a_get(self):
		methods = frappe.allowed_http_methods_for_whitelisted_func
		self.assertEqual(methods[staff_accounts.create_staff_account], ["POST"])
		self.assertEqual(methods[staff_accounts.get_staff_account_options], ["GET"])
