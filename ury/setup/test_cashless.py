"""Cashless payment methods and their accounts (docs/design/cashless-payment-design.md)."""

from unittest.mock import patch

import frappe

from ury.setup.cashless import (
	CASHLESS_MODES,
	apply_cashless_payments,
	ensure_payment_mode,
)
from ury.setup.test_site import ABBR, COMPANY, POS_PROFILE, URYTestCase

CARD_ACCOUNT = f"未収入金（カード会社） - {ABBR}"
RAKUTEN_ACCOUNT = f"未収入金（楽天ペイ） - {ABBR}"


class RolledBackTestCase(URYTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.savepoint("cashless")
		self._forget_cashless()

	def tearDown(self):
		frappe.db.rollback(save_point="cashless")
		frappe.clear_cache()
		super().tearDown()

	def _forget_cashless(self):
		"""The test site already has them (setup_test_site); start from a site that does not."""
		modes = list(CASHLESS_MODES)
		frappe.db.delete("POS Payment Method", {"mode_of_payment": ["in", modes]})
		frappe.db.delete("Mode of Payment Account", {"parent": ["in", modes]})
		frappe.db.delete("Mode of Payment", {"name": ["in", modes]})
		frappe.db.delete("Account", {"name": ["in", [CARD_ACCOUNT, RAKUTEN_ACCOUNT]]})

	def account_of(self, mode):
		return frappe.db.get_value("Mode of Payment Account", {"parent": mode, "company": COMPANY}, "default_account")


class TestApplyCashlessPayments(RolledBackTestCase):
	def test_accounts_are_ledger_bank_accounts_below_accounts_receivable(self):
		apply_cashless_payments()
		for name in (CARD_ACCOUNT, RAKUTEN_ACCOUNT):
			account = frappe.db.get_value("Account", name, ["is_group", "account_type", "parent_account", "root_type"], as_dict=True)
			self.assertEqual(account.is_group, 0, name)
			self.assertEqual(account.account_type, "Bank", name)
			self.assertEqual(account.parent_account, f"Accounts Receivable - {ABBR}", name)
			self.assertEqual(account.root_type, "Asset", name)

	def test_the_three_modes_have_their_accounts(self):
		apply_cashless_payments()
		self.assertEqual(self.account_of("クレジットカード"), CARD_ACCOUNT)
		self.assertEqual(self.account_of("PayPay"), RAKUTEN_ACCOUNT)
		self.assertEqual(self.account_of("楽天ペイ"), RAKUTEN_ACCOUNT)
		for mode in CASHLESS_MODES:
			self.assertEqual(frappe.db.get_value("Mode of Payment", mode, ["type", "enabled"]), ("Bank", 1))

	def test_the_modes_are_added_to_the_pos_profile_after_the_existing_ones(self):
		before = [row.mode_of_payment for row in frappe.get_doc("POS Profile", POS_PROFILE).payments]
		apply_cashless_payments()
		after = [row.mode_of_payment for row in frappe.get_doc("POS Profile", POS_PROFILE).payments]
		self.assertEqual(after[: len(before)], before)
		self.assertEqual(set(after) - set(before) - {"Cash"}, set(CASHLESS_MODES) - set(before))
		self.assertEqual(len(after), len(set(after)))

	def test_a_second_run_changes_nothing(self):
		apply_cashless_payments()
		accounts = frappe.db.count("Account", {"company": COMPANY})
		rows = frappe.db.count("POS Payment Method", {"parent": POS_PROFILE})
		mode_accounts = frappe.db.count("Mode of Payment Account")
		result = apply_cashless_payments()
		self.assertEqual(frappe.db.count("Account", {"company": COMPANY}), accounts)
		self.assertEqual(frappe.db.count("POS Payment Method", {"parent": POS_PROFILE}), rows)
		self.assertEqual(frappe.db.count("Mode of Payment Account"), mode_accounts)
		self.assertEqual(result["created"], [])

	def test_a_company_outside_japan_is_left_alone(self):
		frappe.db.set_value("Company", COMPANY, "country", "India")
		result = apply_cashless_payments()
		self.assertEqual(result["companies"], [])
		self.assertFalse(frappe.db.exists("Account", CARD_ACCOUNT))
		self.assertFalse(frappe.db.exists("Mode of Payment", "PayPay"))

	def test_an_existing_mode_without_an_account_gets_one(self):
		frappe.get_doc({"doctype": "Mode of Payment", "mode_of_payment": "PayPay", "type": "General"}).insert()
		apply_cashless_payments()
		self.assertEqual(self.account_of("PayPay"), RAKUTEN_ACCOUNT)


class TestEnsurePaymentMode(RolledBackTestCase):
	def test_a_custom_cashless_mode_in_japan_gets_its_own_account(self):
		self.assertEqual(ensure_payment_mode("交通系IC", "cashless", COMPANY), "交通系IC")
		account = self.account_of("交通系IC")
		self.assertEqual(account, f"未収入金（交通系IC） - {ABBR}")
		self.assertEqual(frappe.db.get_value("Account", account, ["account_type", "is_group", "parent_account"]), ("Bank", 0, f"Accounts Receivable - {ABBR}"))
		self.assertEqual(frappe.db.get_value("Mode of Payment", "交通系IC", "type"), "Bank")

	def test_a_preset_name_uses_the_shared_account(self):
		ensure_payment_mode("PayPay", "cashless", COMPANY)
		self.assertEqual(self.account_of("PayPay"), RAKUTEN_ACCOUNT)

	def test_outside_japan_the_account_is_a_clearing_account_below_bank_accounts(self):
		frappe.db.set_value("Company", COMPANY, "country", "India")
		ensure_payment_mode("UPI", "cashless", COMPANY)
		self.assertEqual(self.account_of("UPI"), f"UPI Clearing - {ABBR}")
		self.assertEqual(
			frappe.db.get_value("Account", f"UPI Clearing - {ABBR}", ["account_type", "parent_account"]),
			("Bank", f"Bank Accounts - {ABBR}"),
		)

	def test_a_custom_cash_mode_is_of_type_cash_with_a_cash_account(self):
		ensure_payment_mode("商品券", "cash", COMPANY)
		self.assertEqual(frappe.db.get_value("Mode of Payment", "商品券", "type"), "Cash")
		self.assertEqual(frappe.db.get_value("Account", self.account_of("商品券"), "account_type"), "Cash")

	def test_cash_is_left_as_it_is(self):
		before = self.account_of("Cash")
		ensure_payment_mode("Cash", "cash", COMPANY)
		self.assertEqual(self.account_of("Cash"), before)

	def test_the_mode_can_be_used_by_the_mode_of_payment_check(self):
		"""ERPNext only accepts ledger accounts of type Bank / Cash / Receivable."""
		ensure_payment_mode("楽天ペイ", "cashless", COMPANY)
		frappe.get_doc("Mode of Payment", "楽天ペイ").validate()

	def test_a_missing_parent_account_is_an_error_with_a_hint(self):
		with patch("ury.setup.cashless._find_parent", return_value=None):
			with self.assertRaises(frappe.ValidationError) as ctx:
				ensure_payment_mode("PayPay", "cashless", COMPANY)
		self.assertIn(COMPANY, str(ctx.exception))
		self.assertIn("Accounts Receivable", str(ctx.exception))
