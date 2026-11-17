"""The manager makes the accounts of the staff of the shop.

The manager has no right to write a User, a Role or a Has Role: since 2026-11-08 only a System Manager decides who gets which role
(`role_permissions.REVOKED`), because a user who can write roles can give themselves System Manager. A shop changes its staff,
though, and the manager must not have to wait for the owner. So this one narrow call:

- only an account of the three staff roles (`ROLES`: cashier, waiter, kitchen). Never a manager, a URY Admin, a System Manager;
- only into the branch of the manager (a manager of two branches says which);
- only a NEW account: a login that exists (whoever holds it, in any case of letters) is refused and nothing of it is touched;
- the password is made here, random, and is in the answer once; it is not mailed, not logged, and it is not in a variable of a frame
  that can fail (a failure of Frappe logs the variables of the frame: the password would end up in the Error Log);
- every account made is a line of the Activity Log (who, whom, role, branch, when).

Stopping an account and giving a new password stay with the owner (Desk), docs/design/launch-plan.md (2026-11-18).
"""

import re
import secrets

import frappe
from frappe import _
from frappe.utils import now_datetime

from ury.ury.api.invoice_visibility import branches_of
from ury.ury.report_api.utils import require_manager

ROLES = ("URY Cashier", "URY Captain", "URY Kitchen")
ON_THE_REGISTER = ("URY Cashier", "URY Captain")  # added to the POS Profile of the branch (the kitchen screen is not the register)
PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyzACDEFGHJKLMNPQRTUVWXYZ2346789"  # without the letters that look alike
PASSWORD_LENGTH = 14
LOGIN_ID = re.compile(r"^[^@\s]+@[^@\s]+$")
NAME_MAX = 140


def _manager_branches():
	"""The branches of the manager; refuses whoever may not read the reports (the manager's test) or has no branch."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	require_manager()
	branches = branches_of(frappe.session.user)
	if not branches:
		frappe.throw(_("You are not in any branch."), frappe.PermissionError)
	return branches


@frappe.whitelist(methods=["GET"])
def get_staff_account_options():
	"""What the page may offer: whether to show 「アカウントを作る」, the roles, the branches of the manager."""
	try:
		branches = _manager_branches()
	except frappe.PermissionError:
		return {"can_create": False, "roles": [], "branches": []}
	return {"can_create": True, "roles": list(ROLES), "branches": sorted(branches)}


def _clean(value):
	return (value or "").strip() if isinstance(value, str) else ""


@frappe.whitelist(methods=["POST"])
def create_staff_account(first_name, login_id, role, last_name=None, branch=None):
	branches = _manager_branches()
	first_name, last_name, login = _clean(first_name), _clean(last_name), _clean(login_id)
	if not first_name or len(first_name) > NAME_MAX or len(last_name) > NAME_MAX:
		frappe.throw(_("Please write the name (up to {0} characters).").format(NAME_MAX), frappe.ValidationError)
	if not LOGIN_ID.match(login) or len(login) > NAME_MAX:
		frappe.throw(_("The login ID has the form of an e-mail address (name@place, no spaces)."), frappe.ValidationError)
	login = login.lower()
	if role not in ROLES:  # exactly one of the three, as written (not a list, not another case, not a role that rules)
		frappe.throw(_("Only a cashier, a waiter or the kitchen can be made here."), frappe.ValidationError)
	branch = _clean(branch) or None
	if branch is None:
		if len(branches) != 1:
			frappe.throw(_("Say which branch the account is for."), frappe.ValidationError)
		branch = next(iter(branches))
	elif branch not in branches:
		frappe.throw(_("This is not your branch."), frappe.PermissionError)
	if frappe.db.exists("User", login) or frappe.db.exists("User", {"email": login}):
		frappe.throw(_("There is already an account with this login ID."), frappe.ValidationError)

	creator = frappe.session.user
	done = []  # what this call has written, step by step: only that is ever taken back
	frappe.db.savepoint("staff_account")
	try:
		_write(login, first_name, last_name, role, branch, done)
		password = _set_initial_password(login)
		_log(creator, login, first_name, last_name, role, branch)
	except Exception:
		# the frame of a failure is logged by Frappe with its variables: nothing of the password is in this one
		_undo(login, done)
		frappe.throw(_("The account could not be made. Nothing was changed."), frappe.ValidationError)
	return {
		"login_id": login,
		"full_name": f"{first_name} {last_name}".strip(),
		"role": role,
		"branch": branch,
		"initial_password": password,
	}


def _write(login, first_name, last_name, role, branch, done):
	frappe.get_doc(
		{
			"doctype": "User", "email": login, "first_name": first_name, "last_name": last_name or None, "language": "ja",
			"enabled": 1, "send_welcome_email": 0, "roles": [{"role": role}],
		}
	).insert(ignore_permissions=True)
	done.append("user")
	doc = frappe.get_doc("Branch", branch)
	doc.append("user", {"user": login})
	doc.save(ignore_permissions=True)
	done.append(("branch", branch))
	if role in ON_THE_REGISTER:
		profile = frappe.db.get_value("POS Profile", {"branch": branch, "disabled": 0}, "name")
		if profile:
			profile_doc = frappe.get_doc("POS Profile", profile)
			profile_doc.append("applicable_for_users", {"user": login, "default": 1})
			profile_doc.save(ignore_permissions=True)
			done.append(("profile", profile))


def _set_initial_password(login):
	"""Make and set the password and give it back: the only place it is held (a small frame, nothing else in it)."""
	from frappe.utils.password import update_password

	password = "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(PASSWORD_LENGTH))
	update_password(login, password)
	return password


def _log(creator, login, first_name, last_name, role, branch):
	name = f"{first_name} {last_name}".strip()
	frappe.get_doc(
		{
			"doctype": "Activity Log",
			"subject": f"アカウント作成：{creator} が {login}（{name}）を作りました。役割 {role}、分店 {branch}",
			"reference_doctype": "User",
			"reference_name": login,
			"user": creator,
			"status": "Success",
			"communication_date": now_datetime(),
		}
	).insert(ignore_permissions=True)


def _undo(login, done):
	"""Take back what this call wrote, and nothing else. First the savepoint (everything since it); when something has committed in
	between and the savepoint is gone, step by step from `done`. An account that was there before this call is never in `done`."""
	try:
		frappe.db.rollback(save_point="staff_account")
		return
	except Exception:
		pass
	for step in reversed(done):
		if isinstance(step, tuple) and step[0] == "profile":
			doc = frappe.get_doc("POS Profile", step[1])
			doc.applicable_for_users = [row for row in doc.applicable_for_users if row.user != login]
			doc.save(ignore_permissions=True)
		elif isinstance(step, tuple) and step[0] == "branch":
			doc = frappe.get_doc("Branch", step[1])
			doc.user = [row for row in doc.user if row.user != login]
			doc.save(ignore_permissions=True)
		elif step == "user" and frappe.db.exists("User", login):
			frappe.delete_doc("User", login, force=True, ignore_permissions=True)
	if "user" in done:
		frappe.db.delete("Activity Log", {"reference_doctype": "User", "reference_name": login})
