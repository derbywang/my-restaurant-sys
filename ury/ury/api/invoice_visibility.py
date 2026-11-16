"""Who sees which POS Invoices (docs/design/report-permissions.md, "完整版").

A waiter has the POS Invoice permission to take orders. Through the general interfaces (`frappe.client.get_list`,
`get_count`, the report view, `frappe.client.get`) that also lets the waiter add up the day's sales. So whoever may NOT
settle a bill (no `submit` on POS Invoice) sees only the invoices that are still open (docstatus 0) of their own branch;
whoever may settle a bill (cashier, manager, administrator) sees all. The decision is the DocType permission, never a
role name. Two hooks (hooks.py): `permission_query_conditions` for the lists and counts, `has_permission` for one
document. The server's own queries (`get_all`, `ignore_permissions`) are not limited: they are not the waiter's reach.
"""

import frappe

# what looking at an invoice means; writing an open order stays as the permission tables say
SEEING = (None, "read", "select", "print", "email", "report", "export", "share")


def may_see_sales(user=None):
	"""True for whoever may settle a bill: the role permission `submit` on POS Invoice (no document: no hook, no loop)."""
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return bool(frappe.has_permission("POS Invoice", "submit", user=user))


def branches_of(user):
	return frappe.get_all("URY User", filters={"parenttype": "Branch", "user": user}, pluck="parent", distinct=True)


def pos_invoice_query_conditions(user=None, doctype=None):
	user = user or frappe.session.user
	if may_see_sales(user):
		return ""
	branches = branches_of(user)
	in_branch = "`tabPOS Invoice`.branch in ({})".format(", ".join(frappe.db.escape(b) for b in branches)) if branches else "0=1"
	return f"(`tabPOS Invoice`.docstatus = 0 and (ifnull(`tabPOS Invoice`.branch, '') = '' or {in_branch}))"


def pos_invoice_has_permission(doc, ptype=None, user=None, **kwargs):
	"""False for what a waiter must not see; None leaves the decision to the permission tables."""
	user = user or frappe.session.user
	if ptype not in SEEING or may_see_sales(user):
		return None
	if int(doc.get("docstatus") or 0) != 0:
		return False
	branch = doc.get("branch")
	if branch and branch not in branches_of(user):
		return False
	return None


OPEN_STATUSES = ("Draft", "Unbilled")


def require_open_status(status):
	"""For the interfaces that list invoices with raw SQL (`getPosInvoice`, `searchPosInvoice`, `getInvoiceForCashier`):
	the hooks above do not reach raw SQL, so whoever may not settle a bill may ask only for the open orders."""
	if status not in OPEN_STATUSES and not may_see_sales():
		frappe.throw(frappe._("Not permitted to view paid invoices"), frappe.PermissionError)
