"""The signing secret of the QR codes is not for the staff to read.

Whoever has it can make the code of any table. It was an ordinary field: the cashier, the manager, the URY Admin and
the Self Ordering Manager could read it in the Desk and through the API. Now it is a field of permission level 1,
which only a System Manager reads and writes; the server uses it all the same (making and checking the codes).
Run on the test site only.
"""

import frappe
from frappe.utils.password import get_decrypted_password

from ury.setup.test_site import CASHIER, MANAGER, as_user
from ury.ury.api.qr_print import table_qr_print_html
from ury.ury.api.self_ordering import generate_qr_token
from ury.ury.api.test_self_ordering_table import PROFILE, SelfOrderingCase

SUFFIX = "@secret.test.local"
ADMIN = "uryadmin" + SUFFIX
SOM = "selfordering" + SUFFIX
SYSMAN = "sysman" + SUFFIX
USERS = {ADMIN: "URY Admin", SOM: "Self Ordering Manager", SYSMAN: "System Manager"}
SECRET = "self-order-test-secret"


MASK = "*****"


def stored_secret(profile=PROFILE):
	"""The secret as the server reads it (decrypted)."""
	return get_decrypted_password("URY Self Ordering Profile", profile, "qr_signing_secret", raise_exception=False)


def make(email, role):
	frappe.get_doc(
		{"doctype": "User", "email": email, "first_name": "T", "send_welcome_email": 0, "user_type": "System User", "roles": [{"role": role}]}
	).insert(ignore_permissions=True)
	frappe.db.commit()


class TestTheSigningSecret(SelfOrderingCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(self._remove)
		self._remove()
		for email, role in USERS.items():
			make(email, role)

	def _remove(self):
		for email in USERS:
			if frappe.db.exists("User", email):
				frappe.delete_doc("User", email, force=True, ignore_permissions=True)
		frappe.db.commit()

	def seen_by(self, user):
		with as_user(user):
			return frappe.client.get("URY Self Ordering Profile", PROFILE).get("qr_signing_secret")

	def test_the_field_is_of_permission_level_one(self):
		self.assertEqual(frappe.get_meta("URY Self Ordering Profile").get_field("qr_signing_secret").permlevel, 1)

	def test_the_staff_do_not_see_it(self):
		for user in (CASHIER, MANAGER, ADMIN, SOM):
			self.assertFalse(self.seen_by(user), user)

	def test_even_a_system_manager_gets_a_mask_from_the_api(self):
		# a Password field: the form shows dots, the API never gives the value (the server decrypts it itself)
		shown = self.seen_by(SYSMAN)
		self.assertNotEqual(shown, SECRET)
		self.assertTrue(not shown or set(shown) == {"*"}, shown)

	def test_the_field_is_a_password_field_kept_encrypted(self):
		self.assertEqual(frappe.get_meta("URY Self Ordering Profile").get_field("qr_signing_secret").fieldtype, "Password")
		self.assertEqual(stored_secret(), SECRET)
		# no plain text is left in the table of the profile: only stars (Frappe writes as many as the value has)
		in_table = frappe.db.get_value("URY Self Ordering Profile", PROFILE, "qr_signing_secret")
		self.assertTrue(in_table and set(in_table) == {"*"}, in_table)

	def test_the_manager_still_prints_the_codes_and_the_codes_still_work(self):
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, "public_url", "https://order.example.jp")
		with as_user(MANAGER):
			self.assertIn("<svg", table_qr_print_html(PROFILE))
			token = generate_qr_token(PROFILE, "T-01")
		from ury.ury.api.self_ordering import _verify_qr_token

		self.assertEqual(_verify_qr_token(token)[1], "T-01")

	def test_saving_the_profile_as_the_manager_leaves_the_secret_as_it_was(self):
		with as_user(MANAGER):
			doc = frappe.get_doc("URY Self Ordering Profile", PROFILE)
			doc.session_idle_timeout_minutes = 31
			doc.save()
		frappe.db.commit()
		self.assertEqual(stored_secret(), SECRET)


class TestTheSecretThatWasPlainText(SelfOrderingCase):
	"""The patch that moves a plain text secret (the field was a Data field) into the encrypted store."""

	def _plain(self, value, name=PROFILE):
		frappe.db.delete("__Auth", {"doctype": "URY Self Ordering Profile", "name": name, "fieldname": "qr_signing_secret"})
		frappe.db.sql("update `tabURY Self Ordering Profile` set qr_signing_secret = %s where name = %s", (value, name))
		frappe.db.commit()

	def _patch(self):
		from ury.patches.v3_0.encrypt_qr_signing_secret import execute

		execute()
		frappe.db.commit()

	def test_the_value_is_kept_so_the_stickers_stay_valid_and_no_plain_text_is_left(self):
		self._plain("a-plain-text-secret")
		self._patch()
		self.assertEqual(stored_secret(), "a-plain-text-secret")
		self.assertEqual(frappe.db.get_value("URY Self Ordering Profile", PROFILE, "qr_signing_secret"), MASK)

	def test_it_can_be_run_again(self):
		self._plain("a-plain-text-secret")
		self._patch()
		self._patch()
		self.assertEqual(stored_secret(), "a-plain-text-secret")

	def test_a_profile_without_a_secret_is_left_alone(self):
		self._plain(None)
		self._patch()
		self.assertIsNone(stored_secret())
		self.assertFalse(frappe.db.get_value("URY Self Ordering Profile", PROFILE, "qr_signing_secret"))

	def test_a_site_not_yet_patched_still_checks_the_codes(self):
		from ury.ury.api.self_ordering import _verify_qr_token

		with as_user("Administrator"):
			token = generate_qr_token(PROFILE, "T-01")
		self._plain(SECRET)  # the secret is still plain text in the table, nothing in the encrypted store
		self.assertEqual(_verify_qr_token(token)[1], "T-01")

	def test_a_code_made_before_the_patch_is_still_valid_after_it(self):
		"""The stickers on the tables: made with the plain text secret, checked with the encrypted one."""
		from ury.ury.api.self_ordering import _verify_qr_token

		self._plain("the-secret-the-stickers-were-made-with")
		with as_user("Administrator"):
			tokens = {table: generate_qr_token(PROFILE, table) for table in ("T-01", "T-02", "T-03")}
		self._patch()
		self.assertEqual(stored_secret(), "the-secret-the-stickers-were-made-with")
		self.assertEqual(frappe.db.get_value("URY Self Ordering Profile", PROFILE, "qr_signing_secret"), MASK)
		for table, token in tokens.items():
			self.assertEqual(_verify_qr_token(token)[1], table)
