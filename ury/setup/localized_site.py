"""Make the test site look like one that was installed in another language (tests only).

ERPNext names what it creates on install with `_()`: on a Japanese site the root Item Group is
「全てのアイテムグループ」, the Mode of Payment "Cash" is 「現金」, the Customer Group "Individual"
is 「個人」. The test site was installed in English, so code that looks these up by their English
name passes there and fails on a real Japanese site. `localize()` renames them (inside the
caller's savepoint, nothing is committed) so the tests can run the same code on such a site.
"""

import frappe

from ury.setup.test_site import ABBR, COMPANY, require_test_site

# (doctype, English name ERPNext gives it); the field that holds the name as a title
DEFAULTS = (
	("Item Group", "All Item Groups"),
	("Item Group", "Consumable"),
	("Customer Group", "All Customer Groups"),
	("Customer Group", "Individual"),
	("Territory", "All Territories"),
	("Mode of Payment", "Cash"),
	("Price List", "Standard Selling"),
	("Price List", "Standard Buying"),
	("UOM", "Nos"),
)
TITLE_FIELDS = {
	"Item Group": "item_group_name",
	"Customer Group": "customer_group_name",
	"Territory": "territory_name",
	"Mode of Payment": "mode_of_payment",
	"Price List": "price_list_name",
	"UOM": "uom_name",
}
# (table, column) that point at a renamed record and have to follow it
LINKS = {
	"Item Group": (
		("Item Group", "parent_item_group"),
		("Item", "item_group"),
		("URY Production Item Groups", "item_group"),
	),
	"Customer Group": (("Customer Group", "parent_customer_group"), ("Customer", "customer_group")),
	"Territory": (("Territory", "parent_territory"), ("Customer", "territory")),
	"Mode of Payment": (
		("Mode of Payment Account", "parent"),
		("POS Payment Method", "mode_of_payment"),
	),
	"Price List": (
		("Item Price", "price_list"),
		("POS Profile", "selling_price_list"),
		("URY Menu", "price_list"),
	),
	"UOM": (("Item", "stock_uom"),),
}
SINGLES = (
	("Selling Settings", "customer_group"),
	("Selling Settings", "territory"),
	("Selling Settings", "selling_price_list"),
	("Buying Settings", "buying_price_list"),
	("Stock Settings", "stock_uom"),
)


def localize(lang):
	"""Rename the defaults to their `lang` names, set `frappe.local.lang`. Returns {english: local}.
	The caller owns the savepoint and must call `restore_language()` when it rolls back."""
	require_test_site()
	renamed = {}
	for doctype, english in DEFAULTS:
		local = frappe._(english, lang=lang)
		if local == english or not frappe.db.exists(doctype, english) or frappe.db.exists(doctype, local):
			continue
		table = f"`tab{doctype}`"
		frappe.db.sql(
			f"update {table} set name=%s, `{TITLE_FIELDS[doctype]}`=%s where name=%s", (local, local, english)
		)
		for link_doctype, column in LINKS.get(doctype, ()):
			frappe.db.sql(f"update `tab{link_doctype}` set `{column}`=%s where `{column}`=%s", (local, english))
		for single, field in SINGLES:
			if frappe.db.get_single_value(single, field) == english:
				frappe.db.set_single_value(single, field, local)
		renamed[english] = local
	renamed.update(_localize_accounts(lang))
	frappe.clear_cache()
	frappe.local.lang = lang
	return renamed


def _localize_accounts(lang):
	"""ERPNext translates the names of the accounts too ("Accounts Receivable" is 「売掛金」, "Debtors"
	「債務者」, "Cash In Hand" 「手持ちの現金」, "Duties and Taxes" 「関税と税金」 on a Japanese site; checked
	on a site installed in Japanese). Rename the accounts of the test company the same way, and every
	link to them. Returns {old account name: new name}."""
	accounts = frappe.get_all("Account", filters={"company": COMPANY}, fields=["name", "account_name"])
	taken = {row.name for row in accounts}
	mapping = {}
	for row in accounts:
		title = frappe._(row.account_name, lang=lang)
		new = f"{title} - {ABBR}"
		if title == row.account_name or new in taken or new in mapping.values():
			continue
		mapping[row.name] = new
	if not mapping:
		return {}

	for old, new in mapping.items():
		title = new[: -len(f" - {ABBR}")]
		frappe.db.sql("update `tabAccount` set name=%s, account_name=%s where name=%s", (new, title, old))
	for table, column in _account_links():
		_follow(table, column, mapping)
	return mapping


def _account_links():
	"""(table, column) of every Link field to Account, in doctypes and single settings alike."""
	links = set()
	for doctype, field in (("DocField", "parent"), ("Custom Field", "dt")):
		for row in frappe.get_all(doctype, filters={"fieldtype": "Link", "options": "Account"}, fields=[field, "fieldname"]):
			links.add((row[field], row.fieldname))
	return sorted(links)


def _case(column, mapping):
	return "case `%s` %s else `%s` end" % (column, " ".join("when %s then %s" for _ in mapping), column)


def _follow(doctype, column, mapping):
	if column == "name" or not frappe.db.exists("DocType", doctype):
		return
	meta = frappe.get_meta(doctype)
	params = [v for pair in mapping.items() for v in pair]
	if meta.issingle:
		frappe.db.sql(
			"update `tabSingles` set value = case value %s else value end where doctype=%%s and field=%%s and value in (%s)"
			% (" ".join("when %s then %s" for _ in mapping), ", ".join("%s" for _ in mapping)),
			[*params, doctype, column, *mapping],
		)
		return
	if meta.is_virtual or not frappe.db.table_exists(doctype):
		return
	frappe.db.sql(
		"update `tab%s` set `%s` = %s where `%s` in (%s)"
		% (doctype, column, _case(column, mapping), column, ", ".join("%s" for _ in mapping)),
		[*params, *mapping],
	)


def restore_language():
	frappe.local.lang = "en"
	frappe.clear_cache()
