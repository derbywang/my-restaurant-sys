"""The account names the 税理士 recommended (2026-11-09), and the rename of the old ones.

- tax: `CT 10%` / `CT 8%` / `CT 1%`  ->  「仮受消費税等（10％）」「仮受消費税等（軽減8％）」「仮受消費税等（軽減1％）」
- what the card companies still owe: `未収入金（<name>）`  ->  `売掛金（<name>）`

Only the NAMES change. The cashless accounts stay of type Bank: ERPNext wants a customer on every ledger entry of a
Receivable account and the payment entry of a POS invoice has none (docs/design/cashless-payment-design.md).

A rename goes through ERPNext (`update_account_number`), so every link follows (tax templates, item tax templates, modes of
payment, ledger entries). What does NOT follow is the name written inside the text of `item_tax_rate` on the item rows of
bills: a bill printed again would lose its reduced rate. `rewrite_item_tax_rates` changes those too.

Nothing here commits (the caller does: migrate, the setup wizard).
"""

import frappe

TAX_RENAMES = {
	"CT 10%": "仮受消費税等（10％）",
	"CT 8%": "仮受消費税等（軽減8％）",
	"CT 1%": "仮受消費税等（軽減1％）",
}
LEGACY_CASHLESS_PREFIX = "未収入金（"
CASHLESS_PREFIX = "売掛金（"


def _rename(account, new_title):
	from erpnext.accounts.doctype.account.account import update_account_number

	update_account_number(account, new_title)


def rewrite_item_tax_rates(old_name, new_name):
	"""Replace an account name in the `item_tax_rate` text of bill items. Returns how many rows were changed."""
	changed = 0
	for table in ("POS Invoice Item", "Sales Invoice Item"):
		rows = frappe.db.sql(
			f"select name, item_tax_rate from `tab{table}` where item_tax_rate like %(like)s",
			{"like": f"%{old_name}%"},
			as_dict=True,
		)
		for row in rows:
			frappe.db.set_value(table, row.name, "item_tax_rate", row.item_tax_rate.replace(old_name, new_name), update_modified=False)
			changed += 1
	return changed


def rename_legacy_accounts(company):
	"""Give the accounts of `company` the recommended names; returns [(old full name, new full name)] of what it renamed
	(empty when there was nothing to do: safe to run again). An account whose new name is already taken is left alone."""
	abbr = frappe.db.get_value("Company", company, "abbr")
	renamed = []

	for old, new in TAX_RENAMES.items():
		old_name, new_name = f"{old} - {abbr}", f"{new} - {abbr}"
		if frappe.db.exists("Account", old_name) and not frappe.db.exists("Account", new_name):
			_rename(old_name, new)
			rewrite_item_tax_rates(old_name, new_name)
			renamed.append((old_name, new_name))

	for name, title in frappe.get_all(
		"Account", {"company": company, "account_name": ["like", f"{LEGACY_CASHLESS_PREFIX}%"]}, ["name", "account_name"], as_list=True
	):
		new_title = CASHLESS_PREFIX + title[len(LEGACY_CASHLESS_PREFIX):]
		new_name = f"{new_title} - {abbr}"
		if not frappe.db.exists("Account", new_name):
			_rename(name, new_title)
			renamed.append((name, new_name))

	return renamed
