"""Japanese consumption tax structure (docs/design/jp-tax-design.md, 4.1 / 4.2 / 4.7).

`apply_jp_tax_setup()` is idempotent and is run by the `jp_tax_structure` patch and
by `after_install` (installing an app marks its patches as done without running
them). It only touches companies whose country is Japan, and never changes
prices or existing documents.
"""

import frappe
from frappe.utils.nestedset import get_ancestors_of

TEMPLATE_TITLE = "消費税（日本）"
TAX_CATEGORIES = ("店内飲食", "テイクアウト")
VALID_FROM = "2019-10-01"

# One row per rate. Each rate needs its own account: ERPNext keys the per-item
# rate map by account_head, so rows sharing an account cannot be told apart.
# Only the 10% row has a non-zero default rate; the reduced-rate rows are
# switched on per item by the Item Tax Templates below.
RATE_ROWS = (
    {"account_name": "CT 10%", "rate": 10, "default_rate": 10, "description": "消費税 10%"},
    {"account_name": "CT 8%", "rate": 8, "default_rate": 0, "description": "消費税 8%（軽減）"},
    {"account_name": "CT 1%", "rate": 1, "default_rate": 0, "description": "消費税 1%（軽減・時限）"},
)

# Every template lists all three accounts; the ones that do not apply are 0%.
ITEM_TAX_TEMPLATES = {
    "標準10%": {"CT 10%": 10, "CT 8%": 0, "CT 1%": 0},
    "軽減8%": {"CT 10%": 0, "CT 8%": 8, "CT 1%": 0},
    "軽減1%": {"CT 10%": 0, "CT 8%": 0, "CT 1%": 1},
}

# Tax is set only on these three parent groups; kitchen routing keeps using the
# groups underneath them. Every row has a valid_from (see _get_item_tax_template:
# rows without a date are ignored once any dated row is in force).
PARENT_GROUPS = ("食品", "酒類", "非食品")
GROUP_TAXES = {
    "食品": (("店内飲食", "標準10%"), ("テイクアウト", "軽減8%")),
    "酒類": (("店内飲食", "標準10%"), ("テイクアウト", "標準10%")),
    "非食品": (("店内飲食", "標準10%"), ("テイクアウト", "標準10%")),
}

# Single-rate templates that ERPNext's Japan setup ships with. They are replaced by
# the multi-row template above and would only invite mistakes, so they are disabled.
LEGACY_TEMPLATE_TITLES = ("Japan Tax 10%", "Japan Tax 8%")

# Existing leaf groups to hang under a parent group.
GROUPS_TO_MOVE = {"Consumable": "食品"}


def japan_companies():
    return frappe.get_all("Company", filters={"country": "Japan"}, fields=["name", "abbr"])


def is_japan_site():
    return bool(frappe.db.exists("Company", {"country": "Japan"}))


def apply_jp_tax_setup():
    companies = japan_companies()
    if not companies:
        return {"companies": []}

    result = {"companies": [c.name for c in companies], "templates": {}, "disabled": [], "drafts": {}}

    for category in TAX_CATEGORIES:
        _ensure_tax_category(category)

    for group in PARENT_GROUPS:
        _ensure_parent_group(group)
    result["moved"] = _move_groups()

    item_templates = {}
    for company in companies:
        accounts = {row["account_name"]: _ensure_tax_account(company, row) for row in RATE_ROWS}
        template = _ensure_sales_tax_template(company, accounts)
        result["templates"][company.name] = template
        item_templates[company.name] = _ensure_item_tax_templates(company, accounts)

    _ensure_group_taxes(item_templates)

    for company in companies:
        disabled, drafts = _switch_restaurants(company.name, result["templates"][company.name])
        result["disabled"] += disabled
        result["drafts"].update(drafts)
        legacy, legacy_drafts = _disable_legacy_templates(company.name)
        result["disabled"] += legacy
        result["drafts"].update(legacy_drafts)

    result["ungrouped_menu_groups"] = ungrouped_menu_item_groups()
    return result


def _ensure_tax_category(title):
    if not frappe.db.exists("Tax Category", title):
        frappe.get_doc({"doctype": "Tax Category", "title": title}).insert(ignore_permissions=True)


def _ensure_parent_group(name):
    if not frappe.db.exists("Item Group", name):
        frappe.get_doc(
            {
                "doctype": "Item Group",
                "item_group_name": name,
                "parent_item_group": "All Item Groups",
                "is_group": 1,
            }
        ).insert(ignore_permissions=True)


def _move_groups():
    moved = []
    for group, parent in GROUPS_TO_MOVE.items():
        if frappe.db.get_value("Item Group", group, "parent_item_group") == "All Item Groups":
            doc = frappe.get_doc("Item Group", group)
            doc.parent_item_group = parent
            doc.save(ignore_permissions=True)
            moved.append(group)
    return moved


def _ensure_tax_account(company, row):
    name = f"{row['account_name']} - {company.abbr}"
    if frappe.db.exists("Account", name):
        return name

    parent = f"Duties and Taxes - {company.abbr}"
    if not frappe.db.exists("Account", parent):
        frappe.throw(f"Account {parent} not found: create the tax accounts for {company.name} first.")

    frappe.get_doc(
        {
            "doctype": "Account",
            "account_name": row["account_name"],
            "company": company.name,
            "parent_account": parent,
            "account_type": "Tax",
            "tax_rate": row["rate"],
            "is_group": 0,
        }
    ).insert(ignore_permissions=True)
    return name


def _ensure_sales_tax_template(company, accounts):
    name = frappe.db.get_value(
        "Sales Taxes and Charges Template", {"title": TEMPLATE_TITLE, "company": company.name}
    )
    if name:
        return name

    # The new template becomes the company default; make room for it first.
    frappe.db.set_value(
        "Sales Taxes and Charges Template",
        {"company": company.name, "is_default": 1},
        "is_default",
        0,
        update_modified=False,
    )
    doc = frappe.get_doc(
        {
            "doctype": "Sales Taxes and Charges Template",
            "title": TEMPLATE_TITLE,
            "company": company.name,
            "is_default": 1,
            "taxes": [
                {
                    "charge_type": "On Net Total",
                    "account_head": accounts[row["account_name"]],
                    "description": row["description"],
                    "rate": row["default_rate"],
                    "included_in_print_rate": 0,
                }
                for row in RATE_ROWS
            ],
        }
    ).insert(ignore_permissions=True)
    return doc.name


def _ensure_item_tax_templates(company, accounts):
    names = {}
    for title, rates in ITEM_TAX_TEMPLATES.items():
        name = frappe.db.get_value("Item Tax Template", {"title": title, "company": company.name})
        if not name:
            name = (
                frappe.get_doc(
                    {
                        "doctype": "Item Tax Template",
                        "title": title,
                        "company": company.name,
                        "taxes": [
                            {"tax_type": accounts[account_name], "tax_rate": rate}
                            for account_name, rate in rates.items()
                        ],
                    }
                )
                .insert(ignore_permissions=True)
                .name
            )
        names[title] = name
    return names


def _ensure_group_taxes(item_templates):
    """Add the tax rows to the three parent groups, one per company's template."""
    for group, rows in GROUP_TAXES.items():
        doc = frappe.get_doc("Item Group", group)
        existing = {
            (row.item_tax_template, row.tax_category, str(row.valid_from)) for row in doc.get("taxes")
        }
        changed = False
        for templates in item_templates.values():
            for category, title in rows:
                key = (templates[title], category, VALID_FROM)
                if key not in existing:
                    doc.append(
                        "taxes",
                        {
                            "item_tax_template": key[0],
                            "tax_category": category,
                            "valid_from": VALID_FROM,
                        },
                    )
                    changed = True
        if changed:
            doc.save(ignore_permissions=True)


def _switch_restaurants(company, template):
    """Point the restaurants of `company` at the new template and disable the old ones.

    Existing documents are left alone; only the number of drafts that still use a
    disabled template is reported.
    """
    disabled, drafts = [], {}
    for restaurant in frappe.get_all(
        "URY Restaurant", filters={"company": company}, fields=["name", "default_tax_template"]
    ):
        old = restaurant.default_tax_template
        if old and old != template:
            frappe.db.set_value(
                "Sales Taxes and Charges Template", old, {"disabled": 1, "is_default": 0}, update_modified=False
            )
            disabled.append(old)
            drafts[old] = frappe.db.count("POS Invoice", {"docstatus": 0, "taxes_and_charges": old})
        frappe.db.set_value("URY Restaurant", restaurant.name, "default_tax_template", template)
    return disabled, drafts


def _disable_legacy_templates(company):
    disabled, drafts = [], {}
    for name in frappe.get_all(
        "Sales Taxes and Charges Template",
        filters={"company": company, "title": ["in", LEGACY_TEMPLATE_TITLES], "disabled": 0},
        pluck="name",
    ):
        # Only is_default / disabled change; the rows themselves are left as they are.
        frappe.db.set_value(
            "Sales Taxes and Charges Template", name, {"disabled": 1, "is_default": 0}, update_modified=False
        )
        disabled.append(name)
        drafts[name] = frappe.db.count("POS Invoice", {"docstatus": 0, "taxes_and_charges": name})
    return disabled, drafts


def ungrouped_menu_item_groups():
    """Item groups of menu items that have no tax group above them (these items
    would fall back to the default 10% row)."""
    groups = frappe.db.sql(
        """select distinct i.item_group from `tabItem` i
        inner join `tabURY Menu Item` m on m.item = i.name""",
        pluck=True,
    )
    return [g for g in groups if not has_tax_group(g)]


def has_tax_group(item_group):
    return any(g in PARENT_GROUPS for g in [item_group, *get_ancestors_of("Item Group", item_group)])
