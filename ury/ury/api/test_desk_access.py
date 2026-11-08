"""The captain and the cashier work in the POS, not in the Desk (desk_access = 0 on both roles).

Without desk access Frappe makes the account a Website User: the Desk (/app) is closed to it, the POS (/pos), the
password page and the language menu of the POS keep working. The manager and the admin keep the Desk. Run on the
test site only; everything happens in a transaction that is rolled back.
"""

import importlib
import json
import os

import frappe

from ury.setup.test_site import URYTestCase

STAFF = ("URY Captain", "URY Cashier")
DESK = "URY Manager"


def fixture_roles():
	path = os.path.join(frappe.get_app_path("ury"), "fixtures", "role.json")
	with open(path) as f:
		return {r["name"]: r for r in json.load(f)}


def new_account(email, roles):
	# the transaction is rolled back after the class, not after each test
	if frappe.db.exists("User", email):
		frappe.delete_doc("User", email, force=True, ignore_permissions=True)
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": email.split("@")[0],
			"send_welcome_email": 0,
			"enabled": 1,
			"roles": [{"role": r} for r in roles],
		}
	)
	user.insert(ignore_permissions=True)
	return user.name


def user_type(name):
	return frappe.db.get_value("User", name, "user_type")


class SiteGuard(URYTestCase):
	"""Saving a User or a Role can commit, so the rollback of the test class does not always undo it: put the roles
	and the accounts of the site back by hand (feedback: tests that change permissions restore them)."""

	def setUp(self):
		super().setUp()
		roles = {r: frappe.db.get_value("Role", r, ["desk_access", "home_page"], as_dict=True) for r in STAFF}
		users = {
			u.name: u
			for u in frappe.get_all("User", fields=["name", "user_type", "modified", "enabled"], limit_page_length=0)
		}
		self.addCleanup(self._restore, roles, users)

	@staticmethod
	def _restore(roles, users):
		for name in frappe.get_all("User", pluck="name", limit_page_length=0):
			if name not in users:
				frappe.delete_doc("User", name, force=True, ignore_permissions=True)
		for role, values in roles.items():
			frappe.db.set_value("Role", role, dict(values), update_modified=False)
		for name, u in users.items():
			frappe.db.set_value(
				"User", name, {"user_type": u.user_type, "enabled": u.enabled, "modified": u.modified}, update_modified=False
			)
		frappe.db.commit()
		frappe.clear_cache()


class TestRoleFixture(SiteGuard):
	"""What a new site gets (and what every migrate writes back)."""

	def test_the_captain_and_the_cashier_have_no_desk(self):
		roles = fixture_roles()
		for role in STAFF:
			self.assertEqual(roles[role]["desk_access"], 0, role)
			self.assertEqual(roles[role]["home_page"], "pos", role)

	def test_the_manager_keeps_the_desk(self):
		self.assertEqual(fixture_roles()[DESK]["desk_access"], 1)

	def test_the_roles_of_this_site_have_no_desk(self):
		for role in STAFF:
			self.assertEqual(frappe.db.get_value("Role", role, "desk_access"), 0, role)
			self.assertEqual(frappe.db.get_value("Role", role, "home_page"), "pos", role)


class TestAccountsOfTheWizard(SiteGuard):
	def setUp(self):
		super().setUp()
		from ury.ury.api.minimal import business_setup

		self.business_setup = business_setup

	def _create(self, email, role):
		frappe.set_user("Administrator")
		self.business_setup.create_setup_user(email=email, name=email.split("@")[0], role=role)
		return user_type(email)

	def test_a_cashier_account_is_a_website_user(self):
		self.assertEqual(self._create("desk-cashier@test.local", "URY Cashier"), "Website User")

	def test_a_captain_account_is_a_website_user(self):
		self.assertEqual(self._create("desk-captain@test.local", "URY Captain"), "Website User")

	def test_a_manager_account_is_a_system_user(self):
		self.assertEqual(self._create("desk-manager@test.local", "URY Manager"), "System User")


class TestPatch(SiteGuard):
	"""The patch for sites that already have accounts."""

	def setUp(self):
		super().setUp()
		self.module = importlib.import_module("ury.patches.v3_0.staff_without_desk")
		# the state of a site made before this change
		for role in STAFF:
			frappe.db.set_value("Role", role, {"desk_access": 1, "home_page": None})
		self.cashier = new_account("old-cashier@test.local", ["URY Cashier"])
		self.captain = new_account("old-captain@test.local", ["URY Captain"])
		self.both = new_account("old-both@test.local", ["URY Captain", "URY Cashier"])
		self.boss = new_account("old-boss@test.local", ["URY Manager", "URY Cashier"])
		self.manager = new_account("old-manager@test.local", [DESK])
		self.assertEqual(
			[user_type(u) for u in (self.cashier, self.captain, self.both, self.boss, self.manager)],
			["System User"] * 5,
		)

	def test_the_roles_lose_the_desk_and_get_the_pos_as_home(self):
		self.module.execute()
		for role in STAFF:
			self.assertEqual(frappe.db.get_value("Role", role, "desk_access"), 0, role)
			self.assertEqual(frappe.db.get_value("Role", role, "home_page"), "pos", role)

	def test_accounts_with_only_these_roles_become_website_users(self):
		self.module.execute()
		for name in (self.cashier, self.captain, self.both):
			self.assertEqual(user_type(name), "Website User", name)

	def test_an_account_that_also_has_a_desk_role_keeps_the_desk(self):
		self.module.execute()
		self.assertEqual(user_type(self.boss), "System User")
		self.assertEqual(user_type(self.manager), "System User")

	def test_the_roles_of_the_accounts_are_untouched(self):
		before = {u: sorted(frappe.get_roles(u)) for u in (self.cashier, self.boss)}
		self.module.execute()
		frappe.clear_cache(user=self.cashier)
		frappe.clear_cache(user=self.boss)
		self.assertEqual({u: sorted(frappe.get_roles(u)) for u in (self.cashier, self.boss)}, {
			# a Website User no longer gets the automatic "Desk User" role
			self.cashier: [r for r in before[self.cashier] if r != "Desk User"],
			self.boss: before[self.boss],
		})

	def test_disabled_accounts_and_the_other_fields_are_untouched(self):
		frappe.db.set_value("User", self.cashier, "enabled", 0)
		self.module.execute()
		self.assertEqual(frappe.db.get_value("User", self.cashier, "enabled"), 0)
		self.assertEqual(frappe.db.get_value("User", self.cashier, "first_name"), "old-cashier")

	def test_it_can_run_twice(self):
		self.module.execute()
		self.module.execute()
		self.assertEqual(user_type(self.cashier), "Website User")
		self.assertEqual(user_type(self.boss), "System User")
