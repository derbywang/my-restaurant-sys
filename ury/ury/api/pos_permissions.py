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
		"open_shift": bool(frappe.has_permission("POS Opening Entry", "create")),
		"close_shift": bool(frappe.has_permission("POS Closing Entry", "create")),
	}
