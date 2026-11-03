"""The setup and the payment code on a site installed in Japanese, Chinese or Korean.

ERPNext creates the root groups, "Individual", "Consumable", the Mode of Payment "Cash" and more
with `_()`, so on such a site they carry local names. Looking them up by their English name fails
there (the Japanese wizard stopped at 「全てのアイテムグループ」). `localize()` renames them on the
test site inside a savepoint; everything is rolled back.
"""

import frappe
from frappe.utils.nestedset import get_root_of, rebuild_tree

from ury.setup.demo import ensure_master_records_exist
from ury.setup.cashless import CASHLESS_MODES, apply_cashless_payments, ensure_payment_mode
from ury.setup.jp_tax import GROUPS_TO_MOVE, PARENT_GROUPS, RATE_ROWS, _ensure_tax_account, japan_companies
from ury.setup.localized_site import localize, restore_language
from ury.setup.setup_wizard import get_setup_stages
from ury.setup.test_site import ABBR, COMPANY, POS_PROFILE, URYTestCase
from ury.ury.api.minimal.business_setup import get_business_setup, payment_kind
from ury.ury_pos.api import customer_group_and_territory
from ury.setup.wizard_defaults import (
	JP_CUSTOMER,
	apply_all_pos_profile_defaults,
	cash_account,
	ensure_default_customer,
)


class LocalizedSiteCase(URYTestCase):
	LANG = "ja"

	def setUp(self):
		super().setUp()
		frappe.db.savepoint("localized")
		self.names = localize(self.LANG)

	def tearDown(self):
		frappe.db.rollback(save_point="localized")
		restore_language()
		super().tearDown()

	def local(self, english):
		return self.names.get(english, english)

	def run_stages(self):
		args = {"company_name": COMPANY, "setup_ury_demo": 0, "country": "Japan"}
		for stage in get_setup_stages(args):
			for task in stage["tasks"]:
				task["fn"](task["args"])

	def forget_tax_groups(self):
		"""A new site has none of the 食品 / 酒類 / 非食品 groups yet: the stage has to create them."""
		root = get_root_of("Item Group")
		for group in PARENT_GROUPS:
			frappe.db.sql("update `tabItem Group` set parent_item_group=%s where parent_item_group=%s", (root, group))
			frappe.db.delete("Item Group", {"name": group})
		rebuild_tree("Item Group")

	def forget_cashless(self):
		"""A new site has none of the cashless modes and accounts: the setup has to create them."""
		modes = list(CASHLESS_MODES)
		frappe.db.delete("POS Payment Method", {"mode_of_payment": ["in", modes]})
		frappe.db.delete("Mode of Payment Account", {"parent": ["in", modes]})
		frappe.db.delete("Mode of Payment", {"name": ["in", modes]})
		frappe.db.delete("Account", {"account_name": ["in", list(CASHLESS_MODES.values())], "company": COMPANY})

	def forget_default_customer(self):
		frappe.db.set_value("POS Profile", POS_PROFILE, {"customer": None, "account_for_change_amount": None})
		frappe.db.delete("Customer", {"customer_name": JP_CUSTOMER})


class LocalizedSiteTests:
	"""The checks, run once for every language below."""

	def test_the_site_looks_installed_in_that_language(self):
		self.assertNotEqual(self.local("All Item Groups"), "All Item Groups")
		self.assertEqual(get_root_of("Item Group"), self.local("All Item Groups"))
		self.assertFalse(frappe.db.exists("Item Group", "All Item Groups"))

	def test_the_regional_defaults_stage_succeeds(self):
		self.forget_tax_groups()
		frappe.db.set_single_value("Selling Settings", "customer_group", get_root_of("Customer Group"))
		self.run_stages()

		root = get_root_of("Item Group")
		for group in PARENT_GROUPS:
			self.assertEqual(frappe.db.get_value("Item Group", group, "parent_item_group"), root, group)
		for group, parent in GROUPS_TO_MOVE.items():
			self.assertEqual(frappe.db.get_value("Item Group", self.local(group), "parent_item_group"), parent)
		self.assertEqual(
			frappe.db.get_single_value("Selling Settings", "customer_group"), self.local("Individual")
		)

	def test_the_pos_profile_stage_finds_the_cash_account_and_makes_the_default_customer(self):
		self.forget_default_customer()
		apply_all_pos_profile_defaults()
		profile = frappe.db.get_value(
			"POS Profile", POS_PROFILE, ["account_for_change_amount", "customer"], as_dict=True
		)
		self.assertEqual(profile.account_for_change_amount, self.local(f"Cash - {ABBR}"))
		self.assertEqual(
			frappe.db.get_value("Customer", profile.customer, "customer_group"), self.local("Individual")
		)

	def test_the_cash_account_is_found_by_the_type_of_the_mode_not_its_name(self):
		frappe.db.delete("POS Payment Method", {"parent": POS_PROFILE})
		self.assertEqual(cash_account(POS_PROFILE, COMPANY), self.local(f"Cash - {ABBR}"))

	def test_the_default_customer_goes_into_the_individual_group(self):
		self.forget_default_customer()
		customer = ensure_default_customer("Japan")
		self.assertEqual(frappe.db.get_value("Customer", customer, "customer_group"), self.local("Individual"))

	def test_cash_is_the_site_cash_mode_and_no_english_one_is_made(self):
		cash = self.local("Cash")
		self.assertEqual(ensure_payment_mode("Cash", "cash", COMPANY), cash)
		self.assertEqual(ensure_payment_mode(cash, "cash", COMPANY), cash)
		self.assertEqual(bool(frappe.db.exists("Mode of Payment", "Cash")), cash == "Cash")

	def test_the_account_tree_is_translated_like_a_site_installed_in_that_language(self):
		self.assertNotEqual(self.local(f"Accounts Receivable - {ABBR}"), f"Accounts Receivable - {ABBR}")
		self.assertFalse(frappe.db.exists("Account", f"Accounts Receivable - {ABBR}"))
		self.assertTrue(frappe.db.exists("Account", self.local(f"Debtors - {ABBR}")))

	def test_the_cashless_accounts_are_made_below_the_receivables_group(self):
		self.forget_cashless()
		apply_cashless_payments()
		receivables = self.local(f"Accounts Receivable - {ABBR}")
		for mode in CASHLESS_MODES:
			account = frappe.db.get_value(
				"Mode of Payment Account", {"parent": mode, "company": COMPANY}, "default_account"
			)
			self.assertEqual(frappe.db.get_value("Account", account, "parent_account"), receivables, mode)

	def test_the_tax_accounts_are_made_below_the_tax_group(self):
		row = RATE_ROWS[-1]
		account = f"{row['account_name']} - {ABBR}"
		frappe.db.delete("Account", {"name": account})
		self.assertEqual(_ensure_tax_account(japan_companies()[0], row), account)
		self.assertEqual(
			frappe.db.get_value("Account", account, "parent_account"), self.local(f"Duties and Taxes - {ABBR}")
		)

	def test_the_cash_account_for_change_is_below_the_cash_group(self):
		from ury.setup.cashless import parent_account

		self.assertEqual(parent_account(COMPANY, "cash", True), self.local(f"Cash In Hand - {ABBR}"))
		self.assertEqual(parent_account(COMPANY, "cashless", True), self.local(f"Accounts Receivable - {ABBR}"))
		self.assertEqual(parent_account(COMPANY, "cashless", False), self.local(f"Bank Accounts - {ABBR}"))

	def test_a_new_customer_goes_into_the_individual_group_not_the_root(self):
		frappe.db.set_single_value("Selling Settings", "customer_group", get_root_of("Customer Group"))
		frappe.db.set_single_value("Selling Settings", "territory", get_root_of("Territory"))
		group, territory = customer_group_and_territory()
		self.assertEqual(group, self.local("Individual"))
		self.assertEqual(frappe.db.get_value("Territory", territory, "is_group"), 0)

	def test_the_kind_of_a_payment_method_follows_its_type_or_the_cash_mode(self):
		cash = self.local("Cash")
		self.assertEqual(payment_kind("Cash"), "cash")
		self.assertEqual(payment_kind(cash), "cash")
		self.assertEqual(payment_kind("クレジットカード"), "cashless")
		self.assertEqual(payment_kind("anything", "cashless"), "cashless")
		frappe.db.set_value("Mode of Payment", cash, "type", "Bank")
		self.assertEqual(payment_kind(cash), "cashless")

	def test_the_wizard_gets_the_cash_mode_of_the_site(self):
		self.assertEqual(get_business_setup()["data"]["cash_mode"], self.local("Cash"))

	def test_the_demo_masters_do_not_add_english_copies_of_what_exists(self):
		ensure_master_records_exist()
		for doctype, english in (("UOM", "Nos"), ("Price List", "Standard Selling"), ("Price List", "Standard Buying")):
			self.assertEqual(bool(frappe.db.exists(doctype, english)), self.local(english) == english, english)


class TestJapaneseSite(LocalizedSiteTests, LocalizedSiteCase):
	LANG = "ja"


class TestChineseSite(LocalizedSiteTests, LocalizedSiteCase):
	LANG = "zh"


class TestKoreanSite(LocalizedSiteTests, LocalizedSiteCase):
	LANG = "ko"
