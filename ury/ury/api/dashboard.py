import frappe
from frappe import _
from frappe.utils import today

from ury.ury.report_api.utils import require_manager

# What the admin app (/ury) reads through get_module_records: only these DocTypes, and for each only the
# fields its pages show. Nothing else is returned (the User, for one, has an api_key, a password reset key,
# the last IP ... that no page needs). A field the DocType does not have is skipped.
MODULE_RECORD_FIELDS = {
	"Branch": ["name"],
	"URY Room": ["name", "room_name", "room_type", "branch", "kot_printing", "print_format", "block_takeaway"],
	"URY Table": [
		"name", "table_name", "no_of_seats", "minimum_seating", "restaurant", "restaurant_room", "branch",
		"table_shape", "is_take_away", "status",
	],
	"URY Production Unit": ["name", "production", "production_unit_name", "branch"],
	"URY Menu": ["name", "menu_name", "branch"],
	"URY Menu Course": ["name"],
	"Item Group": ["name", "item_group_name"],
	"Item": ["name", "item_name", "standard_rate", "custom_course", "image"],
	"User": ["name", "email", "first_name", "last_name", "full_name", "user_type", "enabled"],
}

@frappe.whitelist()
def get_dashboard_summary(branch=None):
    require_manager()
    filters = {}
    if branch and branch != 'all':
        pass

    return {
        "today_sales": 0,
        "today_orders": 0,
        "occupied_tables": 0,
        "total_tables": frappe.db.count("URY Table") if frappe.db.exists("DocType", "URY Table") else 0,
        "avg_order_value": 0,
        "active_cashiers": frappe.db.count("User", {"enabled": 1}),
        "pending_kitchen_orders": 0,
        "total_menu_items": frappe.db.count("Item") if frappe.db.exists("DocType", "Item") else 0,
    }

@frappe.whitelist()
def get_dashboard_charts(branch=None):
    require_manager()
    return {
        "sales_trend": [],
        "hourly_sales": [],
        "payment_methods": [],
        "order_types": [],
        "top_items": [],
        "revenue_by_branch": [],
        "sales_by_course": [],
    }

@frappe.whitelist()
def get_recent_transactions(branch=None, limit=10):
    require_manager()
    filters = {"docstatus": ["in", [0, 1]]}
    if branch and branch != 'all':
        pass # Add branch filter if applicable for POS Invoice, usually 'custom_branch' or 'branch'
    
    if frappe.db.exists("DocType", "POS Invoice"):
        try:
            invoices = frappe.get_list("POS Invoice",
                filters=filters,
                fields=["name", "customer", "posting_date", "posting_time", "grand_total", "status", "order_type", "restaurant_table as restaurant_table", "owner as cashier"],
                order_by="creation desc",
                limit=int(limit)
            )
            for inv in invoices:
                if not inv.get("status"):
                    inv["status"] = "Draft" if inv.get("docstatus") == 0 else "Paid"
                if not inv.get("order_type"):
                    inv["order_type"] = "Dine In"
            return invoices
        except Exception as e:
            frappe.log_error(f"Error in get_recent_transactions: {str(e)}")
            return []
    return []

@frappe.whitelist()
def get_module_permissions(doctype):
    """What the logged-in user may do with a DocType the admin pages show: {"create": bool, "write": bool}.
    The pages use it to show or hide their Add / Edit buttons (the server still checks on every save).
    Same DocTypes as get_module_records. (Not frappe.has_permission: see below.)"""
    require_manager()
    if doctype not in MODULE_RECORD_FIELDS:
        frappe.throw(_("This DocType cannot be read here."), frappe.PermissionError)
    # the roles' permission on the DocType, not frappe.has_permission(): that one is also true for a user who is
    # shared one document of the DocType, and everybody is shared their own User (they edit their own account)
    granted = frappe.permissions.get_role_permissions(frappe.get_meta(doctype))
    return {"create": bool(granted.get("create")), "write": bool(granted.get("write"))}


@frappe.whitelist()
def get_module_records(doctype, branch=None):
    require_manager()
    if doctype not in MODULE_RECORD_FIELDS:
        frappe.throw(_("This DocType cannot be read here."), frappe.PermissionError)

    meta = frappe.get_meta(doctype)
    filters = {}
    if branch and branch != 'all':
        if meta.has_field("branch"):
            filters["branch"] = branch
        elif meta.has_field("custom_branch"):
            filters["custom_branch"] = branch

    fields = [f for f in MODULE_RECORD_FIELDS[doctype] if f == "name" or meta.has_field(f)]
    # get_list: the permissions of the user still apply
    records = frappe.get_list(doctype, filters=filters, fields=fields, limit_page_length=0)
    if doctype == "User":
        for r in records:
            r["roles"] = frappe.get_all("Has Role", filters={"parent": r.name, "parenttype": "User"}, fields=["role"])
    return records
