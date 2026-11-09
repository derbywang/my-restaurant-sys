"""Account names the 税理士 recommended (2026-11-09): 「仮受消費税等（10％）」「仮受消費税等（軽減8％）」「仮受消費税等（軽減1％）」 for
the tax, 「売掛金（カード会社）」「売掛金（楽天ペイ）」 for what the card companies still owe. Only names change: the types stay
(a Receivable account would need a customer on every payment entry, which the POS payment has none for).
Sites that have the old names (CT 10% ..., 未収入金（...）) are renamed by the setup and by a patch."""

import json
import unittest

import frappe

from ury.setup.account_names import (
	CASHLESS_PREFIX,
	LEGACY_CASHLESS_PREFIX,
	TAX_RENAMES,
	rename_legacy_accounts,
	rewrite_item_tax_rates,
	rewrite_legacy_item_tax_rates,
)
from ury.setup.cashless import CASHLESS_MODES, apply_cashless_payments
from ury.setup.jp_tax import ITEM_TAX_TEMPLATES, RATE_ROWS, apply_jp_tax_setup
from ury.setup.test_site import ABBR, COMPANY, FOOD_ITEM, TABLES, CASHIER, URYFlowTestCase, URYTestCase, open_pos, place_order

TAX_10 = "仮受消費税等（10％）"
TAX_8 = "仮受消費税等（軽減8％）"
TAX_1 = "仮受消費税等（軽減1％）"


class TestTheNames(unittest.TestCase):
	def test_the_tax_accounts_have_the_recommended_names(self):
		self.assertEqual([row["account_name"] for row in RATE_ROWS], [TAX_10, TAX_8, TAX_1])
		self.assertEqual(TAX_RENAMES, {"CT 10%": TAX_10, "CT 8%": TAX_8, "CT 1%": TAX_1})

	def test_the_item_tax_templates_list_those_accounts(self):
		for accounts in ITEM_TAX_TEMPLATES.values():
			self.assertEqual(list(accounts), [TAX_10, TAX_8, TAX_1])

	def test_the_cashless_accounts_are_called_urikakekin(self):
		self.assertEqual(CASHLESS_PREFIX, "売掛金（")
		self.assertEqual(LEGACY_CASHLESS_PREFIX, "未収入金（")
		self.assertEqual(
			CASHLESS_MODES, {"クレジットカード": "売掛金（カード会社）", "PayPay": "売掛金（楽天ペイ）", "楽天ペイ": "売掛金（楽天ペイ）"}
		)


class TestRenamingASite(URYTestCase):
	"""Inside a transaction that is rolled back: the test site may have either spelling."""

	def setUp(self):
		super().setUp()
		frappe.db.savepoint("account_names")
		self.addCleanup(self._back)

	def _back(self):
		frappe.db.rollback(save_point="account_names")
		frappe.clear_cache()

	def _make_legacy(self):
		"""Give the site the old names, whatever it has now."""
		from erpnext.accounts.doctype.account.account import update_account_number

		for old, new in TAX_RENAMES.items():
			if frappe.db.exists("Account", f"{new} - {ABBR}"):
				update_account_number(f"{new} - {ABBR}", old)
		for account in frappe.get_all("Account", {"company": COMPANY, "account_name": ["like", f"{CASHLESS_PREFIX}%"]}, pluck="name"):
			title = frappe.db.get_value("Account", account, "account_name")
			update_account_number(account, LEGACY_CASHLESS_PREFIX + title[len(CASHLESS_PREFIX):])

	def test_the_setup_renames_the_old_tax_accounts_and_what_links_to_them(self):
		self._make_legacy()
		self.assertTrue(frappe.db.exists("Account", f"CT 10% - {ABBR}"))
		result = apply_jp_tax_setup()
		for old, new in TAX_RENAMES.items():
			self.assertFalse(frappe.db.exists("Account", f"{old} - {ABBR}"), old)
			self.assertTrue(frappe.db.exists("Account", f"{new} - {ABBR}"), new)
		template = frappe.get_doc("Sales Taxes and Charges Template", result["templates"][COMPANY])
		self.assertEqual([row.account_head for row in template.taxes], [f"{n} - {ABBR}" for n in (TAX_10, TAX_8, TAX_1)])
		item_template = frappe.get_doc("Item Tax Template", {"title": "標準10%", "company": COMPANY})
		self.assertEqual([row.tax_type for row in item_template.taxes], [f"{n} - {ABBR}" for n in (TAX_10, TAX_8, TAX_1)])
		# still a Tax account with its rate
		self.assertEqual(frappe.db.get_value("Account", f"{TAX_8} - {ABBR}", ["account_type", "tax_rate"]), ("Tax", 8))

	def test_running_the_setup_twice_changes_nothing_more(self):
		self._make_legacy()
		apply_jp_tax_setup()
		before = frappe.get_all("Account", {"company": COMPANY}, pluck="name")
		apply_jp_tax_setup()
		self.assertEqual(sorted(frappe.get_all("Account", {"company": COMPANY}, pluck="name")), sorted(before))

	def test_the_cashless_setup_renames_the_old_accounts_and_the_modes_follow(self):
		self._make_legacy()
		self.assertTrue(frappe.db.exists("Account", f"未収入金（カード会社） - {ABBR}"))
		apply_cashless_payments()
		self.assertFalse(frappe.db.exists("Account", f"未収入金（カード会社） - {ABBR}"))
		self.assertEqual(
			frappe.db.get_value("Mode of Payment Account", {"parent": "クレジットカード", "company": COMPANY}, "default_account"),
			f"売掛金（カード会社） - {ABBR}",
		)
		self.assertEqual(
			frappe.db.get_value("Mode of Payment Account", {"parent": "PayPay", "company": COMPANY}, "default_account"),
			f"売掛金（楽天ペイ） - {ABBR}",
		)

	def test_the_type_stays_bank_not_receivable(self):
		apply_cashless_payments()
		self.assertEqual(frappe.db.get_value("Account", f"売掛金（カード会社） - {ABBR}", "account_type"), "Bank")

	def test_any_old_cashless_account_is_renamed_not_only_the_presets(self):
		from erpnext.accounts.doctype.account.account import update_account_number

		apply_cashless_payments()
		parent = frappe.db.get_value("Account", f"売掛金（カード会社） - {ABBR}", "parent_account")
		frappe.get_doc(
			{"doctype": "Account", "account_name": "未収入金（交通系IC）", "company": COMPANY, "parent_account": parent,
			 "is_group": 0, "account_type": "Bank"}
		).insert(ignore_permissions=True)
		renamed = rename_legacy_accounts(COMPANY)
		self.assertIn(f"未収入金（交通系IC） - {ABBR}", [old for old, _new in renamed])
		self.assertTrue(frappe.db.exists("Account", f"売掛金（交通系IC） - {ABBR}"))

	def test_an_account_that_is_not_ours_is_left_alone(self):
		parent = frappe.db.get_value("Account", f"売掛金（カード会社） - {ABBR}", "parent_account") or frappe.db.get_value(
			"Account", {"company": COMPANY, "account_type": "Tax", "is_group": 0}, "parent_account"
		)
		frappe.get_doc(
			{"doctype": "Account", "account_name": "CT 99%", "company": COMPANY, "parent_account": parent,
			 "is_group": 0, "account_type": "Bank"}
		).insert(ignore_permissions=True)
		rename_legacy_accounts(COMPANY)
		self.assertTrue(frappe.db.exists("Account", f"CT 99% - {ABBR}"))

	def test_a_company_without_the_old_names_is_a_no_op(self):
		self._make_legacy()
		rename_legacy_accounts(COMPANY)
		self.assertEqual(rename_legacy_accounts(COMPANY), [])


class TestTheRatesOfOldBills(URYFlowTestCase):
	"""A bill keeps the rate of each item by the name of its tax account (item_tax_rate): the rename must follow, or an old
	bill printed again would lose its reduced rate. Frappe writes the JSON with ensure_ascii, so a name like
	"CT 8% - 三" is stored as "CT 8% - \\u4e09" (found on the development site: the first version of the patch missed it)."""

	def setUp(self):
		super().setUp()
		open_pos(CASHIER)
		order = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])
		self.row = frappe.db.get_value("POS Invoice Item", {"parent": order}, "name")
		self.old, self.new = f"CT 8% - {ABBR}", f"{TAX_8} - {ABBR}"

	def _value(self):
		return frappe.db.get_value("POS Invoice Item", self.row, "item_tax_rate")

	def test_the_names_in_item_tax_rate_follow_the_rename_as_frappe_writes_them(self):
		# the abbreviation of the shop's company is 三: the JSON of the site has \\u4e09 in it (the test site's TS is ASCII)
		old, new = "CT 8% - 三", f"{TAX_8} - 三"
		frappe.db.set_value("POS Invoice Item", self.row, "item_tax_rate", json.dumps({old: 8.0, "other": 1}))
		self.assertIn("\\u4e09", self._value())  # really escaped, like the data of the site
		self.assertGreaterEqual(rewrite_item_tax_rates(old, new), 1)
		self.assertEqual(json.loads(self._value()), {new: 8.0, "other": 1})

	def test_a_name_written_as_plain_text_follows_too(self):
		frappe.db.set_value("POS Invoice Item", self.row, "item_tax_rate", json.dumps({self.old: 8.0}, ensure_ascii=False))
		rewrite_item_tax_rates(self.old, self.new)
		self.assertEqual(json.loads(self._value()), {self.new: 8.0})

	def test_what_the_first_patch_missed_is_found_later(self):
		frappe.db.set_value(
			"POS Invoice Item", self.row, "item_tax_rate",
			json.dumps({f"CT 10% - {ABBR}": 0.0, self.old: 8.0, f"CT 1% - {ABBR}": 0.0}),
		)
		self.assertGreaterEqual(rewrite_legacy_item_tax_rates(COMPANY), 1)
		self.assertEqual(
			json.loads(self._value()), {f"{TAX_10} - {ABBR}": 0.0, self.new: 8.0, f"{TAX_1} - {ABBR}": 0.0}
		)
		self.assertEqual(rewrite_legacy_item_tax_rates(COMPANY), 0)  # nothing is left: safe to run again
