"""Finding what ERPNext created on install, whatever the language of the site.

ERPNext names much of it with `_()` (root groups, "Individual", "Consumable", the Mode of
Payment "Cash", "Standard Selling", "Nos", "Stores", "Main"), so a site installed in Japanese has
「全てのアイテムグループ」, 「現金」, 「個人」. The chart of accounts is translated too ("Cash In Hand",
"Duties and Taxes" are translated as well). Look things up in this order:

1. by what they are: the root of a tree (`root_of`), the Mode of Payment of type Cash
   (`cash_mode_name`), the group account of an account type (`group_account`);
2. only when nothing but the name tells, by the name ERPNext gave it: the English name or its
   translation in any language of the staff (`existing_name`).
"""

import frappe
from frappe import _
from frappe.utils.nestedset import get_root_of

# the root ERPNext gives each tree; the languages of the staff (ury.ury.api.language)
ROOT_NAMES = {
	"Item Group": "All Item Groups",
	"Customer Group": "All Customer Groups",
	"Territory": "All Territories",
}
LANGUAGES = ("ja", "zh", "ko")


def root_of(doctype):
	"""The root of a tree doctype (Item Group, Customer Group, Territory)."""
	return get_root_of(doctype) or _(ROOT_NAMES[doctype])


def candidates(english):
	"""The English name, its translation in the language of this request, then in the staff languages."""
	names = [english, _(english)]
	names += [frappe._(english, lang=lang) for lang in LANGUAGES]
	return list(dict.fromkeys(names))


def existing_name(doctype, english, filters=None):
	"""The record ERPNext created as `english` (or its translation), None if there is none."""
	for name in candidates(english):
		if frappe.db.exists(doctype, {**(filters or {}), "name": name}):
			return name
	return None


def cash_modes():
	"""The enabled Modes of Payment of type Cash, oldest first. Cash is what the type says, never the name."""
	return frappe.get_all(
		"Mode of Payment", filters={"type": "Cash", "enabled": 1}, pluck="name", order_by="creation, name"
	)


def cash_mode_name():
	"""The Mode of Payment cash is paid with: the one ERPNext created ("Cash" / 「現金」) if it is
	still of type Cash, else the first one of that type."""
	modes = cash_modes()
	for name in candidates("Cash"):
		if name in modes:
			return name
	return modes[0] if modes else None


def group_account(company, account_type):
	"""The group account of `company` that holds the accounts of a type, found by the type and never
	by the name (the chart of accounts is translated too: 「手持ちの現金」, 「売掛金」, 「銀行口座」,
	「関税と税金」 on a Japanese site):
	- Cash ("Cash In Hand"), Bank ("Bank Accounts"), Tax ("Duties and Taxes"): the group with that type;
	- Receivable ("Accounts Receivable"): the group itself has no type, so the parent of the first
	  account of that type (Debtors)."""
	group = frappe.db.get_value(
		"Account",
		{"company": company, "is_group": 1, "account_type": account_type},
		"name",
		order_by="lft",
	)
	if group:
		return group
	parent = frappe.db.get_value(
		"Account",
		{"company": company, "is_group": 0, "account_type": account_type},
		"parent_account",
		order_by="lft",
	)
	return parent if parent and frappe.db.get_value("Account", parent, "is_group") else None


def selling_price_list():
	"""The selling Price List ERPNext created ("Standard Selling"), else any enabled selling one."""
	name = existing_name("Price List", "Standard Selling", {"selling": 1})
	return name or frappe.db.get_value("Price List", {"selling": 1, "enabled": 1}, "name", order_by="creation")


def unit_of_measure(english):
	"""The UOM ERPNext created as `english` ("Nos", "Unit"), None if there is none."""
	return existing_name("UOM", english)
