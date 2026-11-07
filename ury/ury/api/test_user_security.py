"""Nobody makes themselves, or another account, more powerful through the User or the role doctypes.

The waiter and the cashier had write on the higher permission level of the User (roles, user_type, api_key) and
every account may save its own User, so they could add System Manager to themselves; the manager and the URY Admin
write the User at level 0 (new_password included) and could reset the password of any account but the Administrator's.
Now: the staff roles cannot write the level, the manager has no write on User, Role, Role Profile and Module Profile,
the URY Admin only reads the last three, and a user who is not a System Manager can neither touch an account that
is one nor give System Manager or URY Admin to anybody. Every test works on accounts made for it, which are removed
whatever happens (these tests try what must be refused: when it is not refused they must leave nothing behind).
Run on the test site only.
"""

import frappe

from ury.setup.test_site import URYFlowTestCase, as_user
from ury.ury.api.minimal.business_setup import create_setup_user
from ury.user_security import check_privileged_roles

SUFFIX = "@secure.test.local"
CAPTAIN = "captain-s" + SUFFIX
CASHIER = "cashier-s" + SUFFIX
MANAGER = "manager-s" + SUFFIX
URY_ADMIN = "uryadmin-s" + SUFFIX
SYSTEM_MANAGER = "sysmanager-s" + SUFFIX
SYSTEM_MANAGER_TARGET = "target-sysmanager-s" + SUFFIX
STAFF_TARGET = "target-staff-s" + SUFFIX
NEW = "new-s" + SUFFIX
ALL = (CAPTAIN, CASHIER, MANAGER, URY_ADMIN, SYSTEM_MANAGER, SYSTEM_MANAGER_TARGET, STAFF_TARGET, NEW)
STAFF = {CAPTAIN: "URY Captain", CASHIER: "URY Cashier", MANAGER: "URY Manager"}
REFUSED = (frappe.PermissionError, frappe.ValidationError)
PASSWORD = "A-long-first-pass-123"


def remove_all():
	for email in ALL:
		if frappe.db.exists("User", email):
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)
	frappe.db.commit()


def make(email, role):
	frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": "Test",
			"send_welcome_email": 0,
			"user_type": "System User",
			"new_password": PASSWORD,
			"roles": [{"role": role}],
		}
	).insert(ignore_permissions=True)
	frappe.db.commit()


def roles_of(email):
	return set(frappe.get_all("Has Role", filters={"parent": email, "parenttype": "User"}, pluck="role"))


def can(user, ptype, doctype="User", doc=None):
	return bool(frappe.has_permission(doctype, ptype, doc=doc, user=user))


class SecurityCase(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(remove_all)  # registered before anything is made
		remove_all()
		for email, role in {**STAFF, URY_ADMIN: "URY Admin", SYSTEM_MANAGER: "System Manager", SYSTEM_MANAGER_TARGET: "System Manager", STAFF_TARGET: "URY Cashier"}.items():
			make(email, role)

	def password_is_still_the_first(self, email):
		from frappe.utils.password import check_password

		try:
			check_password(email, PASSWORD)
			return True
		except frappe.AuthenticationError:
			return False


def attempt(action):
	"""Do what is not to succeed; a refusal is fine, so is a change that is silently dropped (Frappe resets the fields
	of a permission level the user cannot write): what counts is the state afterwards."""
	try:
		action()
	except REFUSED:
		pass
	frappe.db.rollback()


class TestStaffCannotMakeThemselvesMorePowerful(SecurityCase):
	def test_no_staff_role_adds_a_role_to_its_own_account(self):
		for user in STAFF:
			for role in ("System Manager", "URY Admin"):

				def add():
					with as_user(user):
						doc = frappe.get_doc("User", user)
						doc.append("roles", {"role": role})
						doc.save()

				attempt(add)
				self.assertEqual(roles_of(user), {STAFF[user]}, (user, role))

	def test_no_staff_role_makes_an_account_with_a_role(self):
		for user in STAFF:

			def make_one():
				with as_user(user):
					frappe.get_doc(
						{"doctype": "User", "email": NEW, "first_name": "Someone", "send_welcome_email": 0, "roles": [{"role": "System Manager"}]}
					).insert()

			attempt(make_one)
			self.assertFalse(roles_of(NEW) & {"System Manager", "URY Admin"}, user)
			frappe.delete_doc("User", NEW, force=True, ignore_permissions=True) if frappe.db.exists("User", NEW) else None
			frappe.db.commit()

	def test_staff_still_change_their_own_language_and_password(self):
		for user in STAFF:
			with as_user(user):
				doc = frappe.get_doc("User", user)
				doc.language = "ja"
				doc.new_password = "A-long-second-pass-456"
				doc.save()
			frappe.db.commit()
			self.assertEqual(frappe.db.get_value("User", user, "language"), "ja", user)
			self.assertFalse(self.password_is_still_the_first(user), user)
			self.assertEqual(roles_of(user), {STAFF[user]}, user)

	def test_staff_do_not_touch_the_accounts_of_others(self):
		for user in STAFF:
			for target in (STAFF_TARGET, SYSTEM_MANAGER_TARGET, "Administrator"):
				for ptype in ("write", "create", "delete"):
					if ptype == "create":
						continue  # no document to check
					self.assertFalse(can(user, ptype, doc=frappe.get_doc("User", target)), (user, target, ptype))


class TestTheUryAdminCannotReachASystemManager(SecurityCase):
	def test_the_rights_on_the_accounts(self):
		for target in (SYSTEM_MANAGER_TARGET, "Administrator"):
			doc = frappe.get_doc("User", target)
			for ptype in ("write", "delete", "create", "submit"):
				self.assertFalse(can(URY_ADMIN, ptype, doc=doc), (target, ptype))
		doc = frappe.get_doc("User", STAFF_TARGET)
		for ptype in ("read", "write", "delete"):
			self.assertTrue(can(URY_ADMIN, ptype, doc=doc), ptype)

	def test_a_password_is_not_reset_an_account_is_not_disabled_or_deleted(self):
		def reset():
			with as_user(URY_ADMIN):
				doc = frappe.get_doc("User", SYSTEM_MANAGER_TARGET)
				doc.new_password = "A-long-takeover-pass-789"
				doc.save()

		def disable():
			with as_user(URY_ADMIN):
				doc = frappe.get_doc("User", SYSTEM_MANAGER_TARGET)
				doc.enabled = 0
				doc.save()

		def delete():
			with as_user(URY_ADMIN):
				frappe.delete_doc("User", SYSTEM_MANAGER_TARGET)

		for action in (reset, disable, delete):
			attempt(action)
		self.assertTrue(self.password_is_still_the_first(SYSTEM_MANAGER_TARGET))
		self.assertEqual(frappe.db.get_value("User", SYSTEM_MANAGER_TARGET, "enabled"), 1)
		self.assertTrue(frappe.db.exists("User", SYSTEM_MANAGER_TARGET))

	def test_it_still_looks_after_the_staff(self):
		with as_user(URY_ADMIN):
			doc = frappe.get_doc("User", STAFF_TARGET)
			doc.enabled = 0
			doc.save()
		frappe.db.commit()
		self.assertEqual(frappe.db.get_value("User", STAFF_TARGET, "enabled"), 0)

	def test_a_system_manager_still_may(self):
		with as_user(SYSTEM_MANAGER):
			doc = frappe.get_doc("User", STAFF_TARGET)
			doc.enabled = 0
			doc.save()
		frappe.db.commit()
		self.assertEqual(frappe.db.get_value("User", STAFF_TARGET, "enabled"), 0)

	def test_the_two_privileged_roles_are_given_by_a_system_manager_only(self):
		class Doc:
			def __init__(self, name, roles):
				self.name, self.roles = name, [frappe._dict(role=role) for role in roles]

			def get(self, key):
				return getattr(self, key, None)

		for role in ("System Manager", "URY Admin"):
			with as_user(URY_ADMIN), self.assertRaises(frappe.PermissionError):
				check_privileged_roles(Doc(STAFF_TARGET, ["URY Cashier", role]))
			with as_user(SYSTEM_MANAGER):
				check_privileged_roles(Doc(STAFF_TARGET, ["URY Cashier", role]))
		for role in ("URY Cashier", "URY Captain", "URY Manager"):
			with as_user(URY_ADMIN):
				check_privileged_roles(Doc(NEW, [role]))

	def test_the_wizard_makes_every_staff_role_for_a_ury_admin(self):
		for role in ("URY Cashier", "URY Captain", "URY Manager"):
			with as_user(URY_ADMIN):
				self.assertEqual(create_setup_user(NEW, "Someone", None, role)["status"], "created")
			self.assertEqual(roles_of(NEW), {role})
			frappe.delete_doc("User", NEW, force=True, ignore_permissions=True)
			frappe.db.commit()


class TestTheRoleDoctypes(SecurityCase):
	"""Role, Role Profile and Module Profile decide who gets which role: only a System Manager writes them."""

	def test_staff_and_the_ury_admin_only_read_them(self):
		for doctype in ("Role", "Role Profile", "Module Profile"):
			for user in (MANAGER, URY_ADMIN):
				for ptype in ("write", "create", "delete"):
					self.assertFalse(can(user, ptype, doctype), (doctype, user, ptype))
		self.assertTrue(can(URY_ADMIN, "read", "Role"))
		self.assertTrue(can(MANAGER, "read", "Role"))

	def test_a_system_manager_still_writes_them(self):
		for doctype in ("Role", "Role Profile", "Module Profile"):
			self.assertTrue(can(SYSTEM_MANAGER, "write", doctype), doctype)

	def test_the_manager_does_not_write_or_create_users(self):
		# on the doctype alone "write" is true for everybody (each account is shared with itself): ask for an account
		other = frappe.get_doc("User", STAFF_TARGET)
		self.assertFalse(can(MANAGER, "write", doc=other))
		self.assertFalse(can(MANAGER, "create"))
		self.assertTrue(can(URY_ADMIN, "write", doc=other))
		self.assertTrue(can(URY_ADMIN, "create"))
