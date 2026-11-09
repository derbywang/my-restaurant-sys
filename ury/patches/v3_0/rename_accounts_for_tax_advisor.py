"""The tax accounts and the cashless accounts get the names the 税理士 recommended (2026-11-09).

`CT 10%` / `CT 8%` / `CT 1%` -> 「仮受消費税等（10％）」「仮受消費税等（軽減8％）」「仮受消費税等（軽減1％）」;
`未収入金（…）` -> `売掛金（…）`. Only names: types and rates stay. The links follow through ERPNext's rename; the names inside
`item_tax_rate` of bill items are rewritten too (see ury/setup/account_names.py). Japanese companies only; safe to run twice.
Plain updates, no commit (migrate commits).
"""

import frappe

from ury.setup.account_names import rename_legacy_accounts
from ury.setup.jp_tax import japan_companies


def execute():
	frappe.flags.in_patch = True
	for company in japan_companies():
		rename_legacy_accounts(company.name)
	frappe.clear_cache()
