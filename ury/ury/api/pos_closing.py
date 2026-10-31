"""Which invoices a POS closing covers (docs/design/pos-closing.md).

A shift covers every submitted POS Invoice of the POS Profile that is not consolidated
yet and was posted before the closing time. Not the cashier's own invoices (ERPNext's
rule: the invoice owner is whoever created the order, often a captain), and not only
those posted after the opening: an order taken before the opening and paid after it,
or one the previous closing left out, would otherwise never be consolidated.
"""

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

from ury.ury_pos.api import getBranch

SUPERVISOR_ROLES = {"URY Manager", "System Manager"}


def unconsolidated_invoices(pos_profile, end=None):
	"""Names of the submitted, unconsolidated POS Invoices of `pos_profile` posted up to `end`
	(oldest first)."""
	rows = frappe.db.sql(
		"""
		select name from `tabPOS Invoice`
		where docstatus = 1 and pos_profile = %s
			and ifnull(consolidated_invoice, '') = '' and status != 'Consolidated'
			and timestamp(posting_date, posting_time) <= %s
		order by timestamp(posting_date, posting_time), name
		""",
		(pos_profile, get_datetime(end) if end else now_datetime()),
		pluck="name",
	)
	return rows


@frappe.whitelist()
def get_pos_invoices(start, end, pos_profile, user):
	"""Same signature and result shape as ERPNext's
	`pos_closing_entry.get_pos_invoices`, which this replaces for the URY POS and (through
	`override_whitelisted_methods`) the desk form: every unconsolidated invoice of the
	POS Profile posted up to `end`. `start` and `user` are accepted and ignored."""
	frappe.has_permission("POS Profile", doc=pos_profile, throw=True)
	frappe.has_permission("POS Invoice", "read", throw=True)
	_check_branch(pos_profile)

	return [frappe.get_doc("POS Invoice", name).as_dict() for name in unconsolidated_invoices(pos_profile, end)]


def _check_branch(pos_profile):
	session_user = frappe.session.user
	is_supervisor = session_user == "Administrator" or bool(set(frappe.get_roles(session_user)) & SUPERVISOR_ROLES)

	try:
		session_branch = getBranch()
	except Exception:
		if is_supervisor:
			session_branch = None
		else:
			raise

	profile_branch = frappe.db.get_value("POS Profile", pos_profile, "branch")
	if not profile_branch:
		frappe.throw(_("POS Profile {0} not found.").format(pos_profile), frappe.DoesNotExistError)
	if session_branch and profile_branch != session_branch:
		frappe.throw(
			_("You do not have permission to access invoices for POS Profile {0}.").format(pos_profile),
			frappe.PermissionError,
		)
