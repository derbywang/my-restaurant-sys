"""Cashless payment methods (docs/design/cashless-payment-design.md).

The terminal is not connected: the cashier takes the money on the terminal, then picks the payment
method in the POS and confirms the amount. The bookkeeping follows the company that settles:
- クレジットカード -> 未収入金（カード会社）
- PayPay, 楽天ペイ (both on the 楽天ペイ terminal) -> 未収入金（楽天ペイ）

ERPNext only accepts a ledger account of type Bank, Cash or Receivable for a Mode of Payment, and
a Receivable account needs a customer on every GL entry (the payment entry of a POS invoice has
none), so the accounts are ledger accounts of type Bank below "Accounts Receivable". The names
are meant to be changed (Account > Rename); the Mode of Payment follows.
"""

import frappe
from frappe import _

from ury.setup.jp_tax import japan_companies
from ury.setup.names import candidates, cash_mode_name, group_account

# preset mode -> the account it is settled on (Japan)
CASHLESS_MODES = {
	"クレジットカード": "未収入金（カード会社）",
	"PayPay": "未収入金（楽天ペイ）",
	"楽天ペイ": "未収入金（楽天ペイ）",
}


# the Modes of Payment that are a credit card (the receipt then says it is a credit transaction)
CREDIT_CARD_MODES = ("クレジットカード", "Credit Card")


def apply_cashless_payments():
	"""Idempotent. Japanese companies only: the accounts, the three Modes of Payment with their
	accounts, and the modes in the POS Profiles (added after the existing ones)."""
	result = {"companies": [], "created": []}
	for company in japan_companies():
		result["companies"].append(company.name)
		for mode in CASHLESS_MODES:
			result["created"] += _ensure(mode, "cashless", company.name)
		_add_to_pos_profiles(company.name, list(CASHLESS_MODES))
	return result


def ensure_payment_mode(name, kind, company):
	"""The Mode of Payment `name` with an account for `company` (`kind`: "cash" or "cashless").
	Cash itself is left as ERPNext made it: "Cash" (or its translation) stands for the site's cash
	Mode of Payment, which is named 「現金」 on a Japanese site. Returns the name to use."""
	if kind == "cash" and name in candidates("Cash"):
		existing = cash_mode_name()
		if existing:
			return existing
		name = _("Cash")
	_ensure(name, kind, company)
	return name


def _ensure(name, kind, company):
	"""Create what is missing for one mode; returns what was created."""
	created = []
	japan = frappe.db.get_value("Company", company, "country") == "Japan"
	if not frappe.db.exists("Mode of Payment", name):
		frappe.get_doc(
			{"doctype": "Mode of Payment", "mode_of_payment": name, "type": "Cash" if kind == "cash" else "Bank", "enabled": 1}
		).insert(ignore_permissions=True)
		created.append(f"Mode of Payment {name}")
	if frappe.db.exists("Mode of Payment Account", {"parent": name, "company": company}):
		return created

	title = _account_title(name, kind, japan)
	account, was_created = _ensure_account(company, title, kind, japan)
	if was_created:
		created.append(f"Account {account}")
	mode = frappe.get_doc("Mode of Payment", name)
	mode.append("accounts", {"company": company, "default_account": account})
	mode.save(ignore_permissions=True)
	return created


def _account_title(name, kind, japan):
	if kind == "cash":
		return name
	if japan:
		return CASHLESS_MODES.get(name) or f"未収入金（{name}）"
	return f"{name} Clearing"


def _ensure_account(company, title, kind, japan):
	abbr = frappe.db.get_value("Company", company, "abbr")
	name = f"{title} - {abbr}"
	if frappe.db.exists("Account", name):
		return name, False
	parent = parent_account(company, kind, japan)
	frappe.get_doc(
		{
			"doctype": "Account",
			"account_name": title,
			"company": company,
			"parent_account": parent,
			"is_group": 0,
			"account_type": "Cash" if kind == "cash" else "Bank",
		}
	).insert(ignore_permissions=True)
	return name, True


def parent_account(company, kind, japan):
	parent = _find_parent(company, kind, japan)
	if not parent:
		frappe.throw(
			_(
				"Company {0} has no parent account for the payment account ({1}). Create the group account first, "
				"or set the account of the Mode of Payment by hand, then run the setup again."
			).format(company, _parent_label(kind, japan))
		)
	return parent


def _parent_label(kind, japan):
	return "Cash In Hand" if kind == "cash" else ("Accounts Receivable" if japan else "Bank Accounts")


def _find_parent(company, kind, japan):
	"""The group account the new account goes under: Cash In Hand (cash), Accounts Receivable
	(cashless, Japan) or Bank Accounts (cashless elsewhere)."""
	if kind == "cash":
		return group_account(company, "Cash")
	if japan:
		return group_account(company, "Receivable")
	return group_account(company, "Bank")


def _add_to_pos_profiles(company, modes):
	for profile in frappe.get_all("POS Profile", filters={"company": company}, pluck="name"):
		doc = frappe.get_doc("POS Profile", profile)
		present = {row.mode_of_payment for row in doc.payments}
		missing = [m for m in modes if m not in present]
		for mode in missing:
			doc.append("payments", {"mode_of_payment": mode, "default": 0})
		if missing:
			doc.save(ignore_permissions=True)
