import frappe
from frappe import _

from ury.setup.jp_tax import has_tax_group, is_japan_site


def validate(doc,method):
    update_menu_item(doc,method)
    update_variants_add_on(doc, method)
    warn_item_group_without_tax(doc, method)


def warn_item_group_without_tax(doc, event):
    """On Japanese sites, menu items must sit under 食品 / 酒類 / 非食品: that is where
    the consumption tax is set. Otherwise the item silently gets the default 10%."""
    if not doc.item_group or not is_japan_site():
        return
    if not frappe.db.exists("URY Menu Item", {"item": doc.item_code}):
        return
    if doc.get("taxes") or has_tax_group(doc.item_group):
        return

    frappe.msgprint(
        _("Item group {0} is not under 食品 / 酒類 / 非食品, so no consumption tax rate is set for {1}. It will be taxed at the default 10%.").format(
            frappe.bold(doc.item_group), frappe.bold(doc.item_code)
        ),
        title=_("Consumption tax"),
        indicator="orange",
    )
    
    
def update_menu_item(doc, event):
    menu_items = frappe.get_all('URY Menu Item', filters={'item': doc.item_code})
    for menu_item in menu_items:
        frappe.db.set_value('URY Menu Item', menu_item.name, 'item_name', doc.item_name)

def update_variants_add_on(doc, event):
    if doc.custom_pos_add_on_items:
        for row in doc.custom_pos_add_on_items:
            if not frappe.db.exists("URY Menu Item", {"item": row.item}):
                frappe.throw(f"Item '{row.item}' in POS Add On Items is not in URY Menu")

    if doc.custom_pos_item_variants:
        for row in doc.custom_pos_item_variants:
            if not frappe.db.exists("URY Menu Item", {"item": row.item}):
                frappe.throw(f"Item '{row.item}' in POS Item Variants is not in URY Menu")
