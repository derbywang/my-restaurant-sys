"""Finding what ERPNext created on install, whatever the language of the site (ury.setup.names)."""

import frappe
from frappe.utils.nestedset import get_root_of

from ury.setup.localized_site import localize, restore_language
from ury.setup.names import (
	candidates,
	cash_mode_name,
	cash_modes,
	existing_name,
	group_account,
	root_of,
	selling_price_list,
	unit_of_measure,
)
from ury.setup.test_site import ABBR, COMPANY, URYTestCase


class TestNames(URYTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.savepoint("names")

	def tearDown(self):
		frappe.db.rollback(save_point="names")
		restore_language()
		super().tearDown()

	def test_the_root_is_the_node_without_a_parent(self):
		for doctype in ("Item Group", "Customer Group", "Territory"):
			self.assertEqual(root_of(doctype), get_root_of(doctype))

	def test_the_root_is_found_under_its_local_name(self):
		names = localize("ja")
		self.assertEqual(root_of("Item Group"), names["All Item Groups"])
		self.assertEqual(root_of("Territory"), names["All Territories"])

	def test_candidates_are_the_english_name_and_its_translations_without_repeats(self):
		names = candidates("Individual")
		self.assertEqual(names[0], "Individual")
		self.assertIn("個人", names)
		self.assertEqual(len(names), len(set(names)))

	def test_a_name_is_found_in_english_or_in_any_staff_language(self):
		self.assertEqual(existing_name("Customer Group", "Individual"), "Individual")
		localize("ko")
		self.assertEqual(existing_name("Customer Group", "Individual"), frappe._("Individual", lang="ko"))
		self.assertIsNone(existing_name("Customer Group", "No Such Group"))

	def test_cash_is_found_by_the_type_of_the_mode(self):
		localize("ja")
		self.assertIn("現金", cash_modes())
		self.assertEqual(cash_mode_name(), "現金")
		frappe.db.set_value("Mode of Payment", "現金", "type", "Bank")
		self.assertNotIn("現金", cash_modes())

	def test_a_disabled_cash_mode_is_not_used(self):
		frappe.db.set_value("Mode of Payment", "Cash", "enabled", 0)
		self.assertNotIn("Cash", cash_modes())

	def test_the_group_account_is_found_by_the_account_type(self):
		for account_type, name in (
			("Cash", "Cash In Hand"),
			("Receivable", "Accounts Receivable"),
			("Bank", "Bank Accounts"),
			("Tax", "Duties and Taxes"),
		):
			self.assertEqual(group_account(COMPANY, account_type), f"{name} - {ABBR}", account_type)

	def test_the_group_account_is_found_on_a_site_with_a_translated_chart_of_accounts(self):
		for lang in ("ja", "zh", "ko"):
			names = localize(lang)
			for account_type, name in (
				("Cash", "Cash In Hand"),
				("Receivable", "Accounts Receivable"),
				("Bank", "Bank Accounts"),
				("Tax", "Duties and Taxes"),
			):
				account = group_account(COMPANY, account_type)
				self.assertEqual(account, names[f"{name} - {ABBR}"], f"{lang} {account_type}")
				self.assertEqual(frappe.db.get_value("Account", account, "is_group"), 1)
			frappe.db.rollback(save_point="names")
			frappe.db.savepoint("names")

	def test_receivables_have_no_group_of_their_own_type_so_the_parent_of_the_debtors_is_used(self):
		self.assertFalse(frappe.db.exists("Account", {"company": COMPANY, "is_group": 1, "account_type": "Receivable"}))
		debtors = frappe.db.get_value("Account", {"company": COMPANY, "is_group": 0, "account_type": "Receivable"}, "parent_account")
		self.assertEqual(group_account(COMPANY, "Receivable"), debtors)

	def test_the_selling_price_list_and_the_unit_are_the_sites_own(self):
		names = localize("ja")
		self.assertEqual(selling_price_list(), names["Standard Selling"])
		self.assertEqual(unit_of_measure("Nos"), names["Nos"])
