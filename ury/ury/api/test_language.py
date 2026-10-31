import frappe
from frappe.tests.utils import FrappeTestCase

from ury.ury.api.language import get_language_options, set_staff_language


class TestStaffLanguage(FrappeTestCase):
	def setUp(self):
		# Tests run on the dev site: remember and restore the real users' languages.
		self._original = {
			user: frappe.db.get_value("User", user, "language") for user in ("Administrator", "Guest")
		}
		self.addCleanup(self._restore)

	def _restore(self):
		frappe.set_user("Administrator")
		for user, lang in self._original.items():
			frappe.db.set_value("User", user, "language", lang)
		frappe.db.commit()

	def test_options_are_the_four_menu_languages(self):
		self.assertEqual([o["code"] for o in get_language_options()], ["ja", "zh", "ko", "en"])

	def test_guest_is_rejected(self):
		frappe.set_user("Guest")
		self.assertRaises(frappe.PermissionError, set_staff_language, "ja")
		self.assertEqual(frappe.db.get_value("User", "Guest", "language"), self._original["Guest"])

	def test_unsupported_language_is_rejected(self):
		frappe.set_user("Administrator")
		for lang in ("fr", "ar", "xx", ""):
			self.assertRaises(frappe.ValidationError, set_staff_language, lang)
		self.assertEqual(frappe.db.get_value("User", "Administrator", "language"), self._original["Administrator"])

	def test_updates_only_current_user(self):
		frappe.set_user("Administrator")
		self.assertEqual(set_staff_language("zh"), "zh")
		self.assertEqual(frappe.db.get_value("User", "Administrator", "language"), "zh")
		self.assertEqual(frappe.db.get_value("User", "Guest", "language"), self._original["Guest"])

	def test_clears_user_cache(self):
		frappe.set_user("Administrator")
		frappe.cache().hset("bootinfo", "Administrator", {"lang": "stale"})
		set_staff_language("ko")
		self.assertIsNone(frappe.cache().hget("bootinfo", "Administrator"))
