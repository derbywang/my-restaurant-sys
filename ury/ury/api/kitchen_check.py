"""Dishes that no kitchen makes.

A dish is made by a production unit when its item group is one of the unit's item groups
(URY Production Unit > Item Groups). A dish whose group is in no unit of the branch gets no kitchen ticket: it is
ordered, billed and never cooked. This module finds such dishes (on a menu, or in an order being sent) and tells
the registers when an order has one.
"""

import frappe
from frappe import _

# One sentence for the register (the notification), the staff member who took the order, and the menu warning, so
# that they read alike. The Japanese is in translations/ja.csv.
NO_TICKET = "No kitchen ticket was made for: {0}. Please check with the kitchen."
MENU_WARNING = "No production unit makes these dishes, so they will get no kitchen ticket: {0}"


def production_item_groups(branch):
    """The item groups the production units of `branch` make."""
    units = frappe.get_all("URY Production Unit", filters={"branch": branch}, pluck="name")
    if not units:
        return set()
    return set(
        frappe.get_all(
            "URY Production Item Groups",
            filters={"parent": ["in", units], "parenttype": "URY Production Unit"},
            pluck="item_group",
        )
    )


def items_without_kitchen(branch, item_codes):
    """[{item_code, item_name, item_group}] of the dishes (of `item_codes`) that no production unit of the branch makes."""
    groups = production_item_groups(branch)
    found, seen = [], set()
    for code in item_codes:
        if code in seen:
            continue
        seen.add(code)
        item_name, item_group = frappe.db.get_value("Item", code, ["item_name", "item_group"]) or (code, None)
        if item_group not in groups:
            found.append({"item_code": code, "item_name": item_name, "item_group": item_group})
    return found


@frappe.whitelist()
def menu_items_without_kitchen(branch=None):
    """Read only. [{menu, branch, item, item_name, item_group}]: the dishes on an enabled menu (and not switched off)
    that no production unit of the menu's branch makes. To run at deployment and after the menu was changed:

        bench --site <site> execute ury.ury.api.kitchen_check.menu_items_without_kitchen
    """
    frappe.only_for(("System Manager", "URY Manager", "URY Cashier", "URY Captain", "Administrator"))
    filters = {"enabled": 1}
    if branch:
        filters["branch"] = branch
    rows = []
    for menu in frappe.get_all("URY Menu", filters=filters, fields=["name", "branch"]):
        codes = frappe.get_all("URY Menu Item", filters={"parent": menu.name, "disabled": 0}, pluck="item")
        for found in items_without_kitchen(menu.branch, codes):
            rows.append(
                {
                    "menu": menu.name,
                    "branch": menu.branch,
                    "item": found["item_code"],
                    "item_name": found["item_name"],
                    "item_group": found["item_group"],
                }
            )
    return rows


def warn_menu_without_kitchen(menu):
    """When a menu is saved: say which of its dishes no kitchen makes (the save is not stopped)."""
    if not menu.get("branch") or not menu.get("enabled"):
        return
    codes = [row.item for row in menu.items if row.item and not row.get("disabled")]
    names = [found["item_name"] or found["item_code"] for found in items_without_kitchen(menu.branch, codes)]
    if names:
        frappe.msgprint(_(MENU_WARNING).format(", ".join(names)), indicator="orange", alert=False)


def announce_no_kitchen(branch, invoice, table, dishes):
    """The order is saved but these dishes get no kitchen ticket: tell the registers of the branch on the channels they
    listen to for kitchen errors (kot_error_<branch>_<production unit>). Sent once the order is committed."""
    if not dishes:
        return
    try:
        for unit in frappe.get_all("URY Production Unit", filters={"branch": branch}, pluck="name"):
            frappe.publish_realtime(
                f"kot_error_{branch}_{unit}",
                {
                    "kind": "no_kitchen",
                    "invoice": invoice,
                    "table": table,
                    "branch": branch,
                    "production": unit,
                    "items": [dish["item_name"] or dish["item_code"] for dish in dishes],
                },
                after_commit=True,
            )
    except Exception as e:  # telling the register must not undo the order
        frappe.log_error(f"Could not announce dishes without a kitchen: {e}", "KOT Error")
