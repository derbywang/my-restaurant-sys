import frappe
from frappe.tests.utils import FrappeTestCase

from ury.setup.test_site import MANAGER, URYTestCase, as_user
from ury.ury.api.language import get_language_options, set_staff_language
from ury.ury.api.ury_kot_display import get_site_name


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


class TestKitchenScreenLanguage(URYTestCase):
	"""The kitchen screen speaks the language of the user who is logged in (`get_site_name` says it)."""

	def setUp(self):
		super().setUp()
		frappe.db.savepoint("kitchen_language")
		self.addCleanup(frappe.db.rollback, save_point="kitchen_language")
		self.addCleanup(frappe.clear_cache)

	def _lang_of(self, user, language, system="ja"):
		frappe.db.set_value("User", user, "language", language)
		frappe.db.set_single_value("System Settings", "language", system)
		with as_user(user):
			return get_site_name()["lang"]

	def test_it_is_the_language_of_the_user(self):
		for language in ("ja", "zh", "ko", "en"):
			self.assertEqual(self._lang_of(MANAGER, language), language)

	def test_a_regional_language_is_the_staff_language_it_belongs_to(self):
		self.assertEqual(self._lang_of(MANAGER, "zh-TW"), "zh")
		self.assertEqual(self._lang_of(MANAGER, "en-GB"), "en")

	def test_a_user_without_a_language_gets_the_language_of_the_site(self):
		self.assertEqual(self._lang_of(MANAGER, None, system="ko"), "ko")

	def test_a_language_the_screen_does_not_have_falls_back_to_japanese(self):
		self.assertEqual(self._lang_of(MANAGER, "fr", system="fr"), "ja")

	def test_the_site_name_is_still_given(self):
		with as_user(MANAGER):
			self.assertEqual(get_site_name()["site_name"], frappe.local.site)

	def test_a_guest_gets_the_site_language_too(self):
		frappe.db.set_single_value("System Settings", "language", "ko")
		with as_user("Guest"):
			self.assertEqual(get_site_name()["lang"], "ko")
