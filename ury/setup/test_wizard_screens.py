"""What the first wizard screens offer and leave behind: languages, defaults, the Japan date format,
the default app (docs/design/ui-todo.md, wizard problems)."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ury.setup.jp_currency import DATE_FORMAT, apply_jp_date_format
from ury.setup.wizard_defaults import apply_company_defaults, apply_default_app
from ury.ury.api.minimal.business_setup import get_business_setup
from ury.ury.api.minimal.setup_organization import get_setup_defaults


class TestSetupDefaults(FrappeTestCase):
	def test_the_languages_are_the_staff_languages(self):
		languages = get_setup_defaults()["languages"]
		self.assertEqual([lang["label"] for lang in languages], ["日本語", "中文", "한국어", "English"])

	def test_the_value_is_the_language_name_frappe_maps_back_to_a_code(self):
		from frappe.desk.page.setup_wizard.setup_wizard import get_language_code

		languages = get_setup_defaults()["languages"]
		self.assertEqual([get_language_code(lang["value"]) for lang in languages], ["ja", "zh", "ko", "en"])

	def test_the_defaults_are_japan_and_japanese(self):
		defaults = get_setup_defaults()
		self.assertEqual(defaults["default_country"], "Japan")
		self.assertEqual(defaults["default_language"], "日本語")
		self.assertIn("Japan", defaults["countries"])
		self.assertIn("日本語", [lang["value"] for lang in defaults["languages"]])


class TestJapanDateFormat(FrappeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.savepoint("date_format")
		self.addCleanup(frappe.db.rollback, save_point="date_format")
		frappe.db.set_single_value("System Settings", "date_format", "dd-mm-yyyy")
		frappe.clear_cache()

	def _format(self):
		return frappe.db.get_single_value("System Settings", "date_format")

	def test_a_japanese_site_gets_year_month_day(self):
		with patch("ury.setup.jp_currency.has_japan_company", return_value=True):
			result = apply_jp_date_format()
		self.assertEqual(self._format(), DATE_FORMAT)
		self.assertEqual(DATE_FORMAT, "yyyy-mm-dd")
		self.assertEqual(result, {"applied": True, "changed": ["System Settings.date_format"]})

	def test_it_is_idempotent(self):
		with patch("ury.setup.jp_currency.has_japan_company", return_value=True):
			apply_jp_date_format()
			self.assertEqual(apply_jp_date_format()["changed"], [])

	def test_another_country_is_left_alone(self):
		with patch("ury.setup.jp_currency.has_japan_company", return_value=False):
			result = apply_jp_date_format()
		self.assertEqual(self._format(), "dd-mm-yyyy")
		self.assertEqual(result, {"applied": False, "changed": []})

	def test_the_wizard_stage_applies_it_on_a_japanese_site(self):
		with patch("ury.setup.jp_tax.is_japan_site", return_value=True), patch(
			"ury.setup.jp_tax.apply_jp_tax_setup"
		), patch("ury.setup.jp_currency.apply_jpy_format"), patch(
			"ury.setup.wizard_defaults._set_selling_defaults"
		), patch("ury.setup.jp_currency.has_japan_company", return_value=True):
			apply_company_defaults()
		self.assertEqual(self._format(), DATE_FORMAT)


class TestDefaultApp(FrappeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.savepoint("default_app")
		self.addCleanup(frappe.db.rollback, save_point="default_app")
		frappe.clear_cache()

	def _default_app(self):
		return frappe.db.get_single_value("System Settings", "default_app")

	def test_ury_becomes_the_default_app(self):
		frappe.db.set_single_value("System Settings", "default_app", None)
		self.assertEqual(apply_default_app(), {"changed": True})
		self.assertEqual(self._default_app(), "ury")

	def test_another_choice_of_the_owner_is_kept(self):
		frappe.db.set_single_value("System Settings", "default_app", "erpnext")
		self.assertEqual(apply_default_app(), {"changed": False})
		self.assertEqual(self._default_app(), "erpnext")

	def test_login_then_goes_straight_to_ury(self):
		from frappe.apps import get_default_path

		frappe.db.set_single_value("System Settings", "default_app", None)
		apply_default_app()
		frappe.clear_cache()
		self.assertEqual(get_default_path(), "/ury")

	def test_the_company_stage_sets_it_on_every_site(self):
		frappe.db.set_single_value("System Settings", "default_app", None)
		with patch("ury.setup.jp_tax.is_japan_site", return_value=False):
			apply_company_defaults()
		self.assertEqual(self._default_app(), "ury")


class TestBusinessSetupCurrency(FrappeTestCase):
	def test_the_company_currency_comes_with_the_setup_data(self):
		data = get_business_setup()["data"]
		self.assertEqual(data["currency"], frappe.db.get_value("Company", data["company"], "default_currency"))
