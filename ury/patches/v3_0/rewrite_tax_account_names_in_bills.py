"""The old tax account names that are still written in the bill items (2026-11-09).

`rename_accounts_for_tax_advisor` renamed the accounts but looked for the names in `item_tax_rate` the way they are written
as plain text; Frappe writes that JSON with ensure_ascii ("CT 8% - 三"), so the item rows kept the old names and an old
bill printed again would have lost its reduced rate. `account_names.rewrite_item_tax_rates` now replaces both spellings; this
patch does it for the rows the first patch left. Japanese companies only; safe to run twice. No commit (migrate commits).
"""

import frappe

from ury.setup.account_names import rewrite_legacy_item_tax_rates
from ury.setup.jp_tax import japan_companies


def execute():
	for company in japan_companies():
		rewrite_legacy_item_tax_rates(company.name)
	frappe.clear_cache()
