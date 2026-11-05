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
