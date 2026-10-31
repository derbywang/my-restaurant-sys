from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ury.ury.api.minimal.business_setup import _site_default_currency


class TestSiteDefaultCurrency(FrappeTestCase):
	@patch("ury.ury.api.minimal.business_setup.frappe.defaults.get_global_default", return_value="USD")
	def test_global_default_wins(self, _mock_default):
		self.assertEqual(_site_default_currency(), "USD")

	@patch("ury.ury.api.minimal.business_setup.frappe.db.get_single_value", return_value="Japan")
	@patch(
		"ury.ury.api.minimal.business_setup.frappe.defaults.get_global_default",
		side_effect=lambda key: {"currency": None, "country": None}[key],
	)
	def test_falls_back_to_the_wizard_country_currency(self, _mock_default, _mock_single):
		self.assertEqual(_site_default_currency(), "JPY")

	@patch("ury.ury.api.minimal.business_setup.frappe.db.get_single_value", return_value=None)
	@patch("ury.ury.api.minimal.business_setup.frappe.defaults.get_global_default", return_value=None)
	def test_raises_instead_of_guessing(self, _mock_default, _mock_single):
		self.assertRaises(frappe.ValidationError, _site_default_currency)


class TestDefaultMenuItemGroup(FrappeTestCase):
	@patch("ury.setup.jp_tax.is_japan_site", return_value=True)
	@patch(
		"ury.ury.api.item_group.get_menu_item_groups",
		return_value=[{"name": "Bar", "parent": "酒類"}, {"name": "Kitchen", "parent": "食品"}],
	)
	def test_japan_wizard_items_go_under_food(self, _groups, _japan):
		from ury.ury.api.minimal.business_setup import _default_menu_item_group

		self.assertEqual(_default_menu_item_group(), "Kitchen")
