"""Who may do what in the POS (the store's rule: only a cashier settles a bill).

The DocType permission is the truth: `get_pos_permissions` answers for the POS with
`frappe.has_permission`, never with a role name, and the billing endpoints call
`require_billing_permission` before they touch the bill. A captain (URY Captain) takes and adds
orders and prints the bill for the guest; paying, 会計合算 / 解除, 会計分割, discounts, cancelling
and opening / closing the shift need what a cashier has (submit on POS Invoice, create on POS
Opening / Closing Entry).
"""

import frappe
from frappe import _

# roles that may give a discount at the register (the check make_invoice has always made)
DISCOUNT_ROLES = {"Administrator", "System Manager", "URY Admin", "URY Manager", "URY Cashier"}


def can_bill(doc=None):
	"""Settling a bill is submitting the POS Invoice."""
	return bool(frappe.has_permission("POS Invoice", "submit", doc=doc))


def can_view_sales():
	"""The sales figures of the POS dashboard: whoever may settle a bill (cashier, manager, admin), not a captain."""
	return can_bill()


def require_sales_view():
	"""Raise PermissionError for a user who may not see the sales figures. Every function behind the POS
	dashboard calls this FIRST, before it reads its cache (the cache is shared by all users)."""
	if not can_view_sales():
		frappe.throw(_("You do not have permission to see the sales figures."), frappe.PermissionError)


def require_billing_permission(doc=None):
	"""Raise PermissionError, before anything is written, for a user who may not settle bills."""
	if not can_bill(doc):
		frappe.throw(
			_("Only a cashier can do this. Ask the cashier to take the payment, merge or split the bill."),
			frappe.PermissionError,
		)


def can_reduce_sent_items(pos_profile):
	"""Taking back a dish that already went to the kitchen (fewer, or none at all).

	Both must hold: the store allows it (the POS Profile switch `remove_items`) and the user may
	cancel POS Invoices (the cashier and the manager; a captain may add dishes but not take them back).
	"""
	if not pos_profile or not frappe.has_permission("POS Invoice", "cancel"):
		return False
	return bool(frappe.db.get_value("POS Profile", pos_profile, "remove_items"))


@frappe.whitelist()
def get_shift_state():
	"""Is the register of the user's shop open? A waiter works on the shift the cashier opened: she has none of her own.

	The question ERPNext asks when an order is saved: an open, submitted POS Opening Entry of the POS Profile, whoever
	opened it. Read-only (a GET is rolled back; nothing is written here)."""
	profiles = _profiles_of_branch()
	entry = None
	if profiles:
		entry = frappe.db.get_value(
			"POS Opening Entry",
			{"pos_profile": ["in", profiles], "status": "Open", "docstatus": 1},
			["name", "user"],
			order_by="period_start_date desc",
			as_dict=True,
		)
	return {"open": bool(entry), "opened_by": entry.user if entry else None}


def _profiles_of_branch():
	from ury.ury_pos.api import getBranch

	try:
		branch = getBranch()
	except frappe.ValidationError:
		return []
	return frappe.get_all("POS Profile", filters={"branch": branch}, pluck="name") if branch else []


def _profile_of_user():
	"""The POS Profile of the user's branch (what `get_captain_context` also uses); None when there is none."""
	from ury.ury_pos.api import getBranch

	try:
		branch = getBranch()
	except frappe.ValidationError:
		return None
	return frappe.db.exists("POS Profile", {"branch": branch}) if branch else None


@frappe.whitelist()
def get_pos_permissions():
	"""What the current user may do in the POS; the POS shows only these actions."""
	billing = can_bill()
	return {
		"take_orders": bool(frappe.has_permission("POS Invoice", "create")),
		"print_bill": bool(frappe.has_permission("POS Invoice", "print")),
		"settle_payment": billing,
		# the dashboard page with the day's sales: whoever may settle a bill
		"view_dashboard": can_view_sales(),
		"cancel_order": bool(frappe.has_permission("POS Invoice", "cancel")),
		"apply_discount": billing and bool(DISCOUNT_ROLES.intersection(frappe.get_roles())),
		"merge_bills": billing,
		"unmerge_bills": billing,
		"split_bill": billing,
		"reduce_sent_items": can_reduce_sent_items(_profile_of_user()),
		# opening a table for self ordering: whoever takes orders (the POS also checks the branch's Self Ordering Profile)
		"open_self_order": bool(frappe.has_permission("POS Invoice", "create")),
		"open_shift": bool(frappe.has_permission("POS Opening Entry", "create")),
		"close_shift": bool(frappe.has_permission("POS Closing Entry", "create")),
	}
