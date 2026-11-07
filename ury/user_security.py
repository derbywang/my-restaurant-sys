"""Keep the accounts of the owners out of reach of the staff.

A user who is not a System Manager (a URY Admin, say) must not touch an account that is one: not write it (the
password, `enabled`, the roles), not delete it. And nobody but a System Manager gives the roles System Manager or
URY Admin, whatever the permission tables say: the tables decided who may write the roles of a User, and once they
were wrong (the waiter could make themselves a System Manager).
"""

import frappe
from frappe import _

PRIVILEGED_ROLES = ("System Manager", "URY Admin")
READ_ONLY = (None, "read", "select", "print", "email", "report", "export", "share")


def is_system_manager(user):
	return user == "Administrator" or "System Manager" in frappe.get_roles(user)


def roles_in_database(name):
	return set(frappe.get_all("Has Role", filters={"parent": name, "parenttype": "User"}, pluck="role"))


def user_has_permission(doc, ptype=None, user=None, **kwargs):
	"""`has_permission` hook of the User: False for what a non-System-Manager does to a System Manager's account."""
	user = user or frappe.session.user
	if ptype in READ_ONLY or is_system_manager(user):
		return None
	name = doc if isinstance(doc, str) else doc.get("name")
	if not name or name == user:
		return None  # one's own account (language, password) is one's own business
	if name == "Administrator" or "System Manager" in roles_in_database(name):
		return False
	return None


def check_privileged_roles(doc, method=None):
	"""`validate` hook of the User: only a System Manager gives System Manager or URY Admin."""
	if frappe.flags.in_install or frappe.flags.in_patch or frappe.flags.in_migrate:
		return
	if is_system_manager(frappe.session.user):
		return
	wanted = {row.role for row in (doc.get("roles") or [])} & set(PRIVILEGED_ROLES)
	if not wanted:
		return
	has = roles_in_database(doc.name) if frappe.db.exists("User", doc.name) else set()
	if wanted - has:
		frappe.throw(
			_("Only a System Manager may give the roles {0}").format(", ".join(PRIVILEGED_ROLES)), frappe.PermissionError
		)
