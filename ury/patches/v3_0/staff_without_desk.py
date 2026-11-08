"""The captain and the cashier work in the POS, not in the Desk.

Both roles lose `desk_access` and get `pos` as their home page (where Frappe sends a user after login). An account
that has only roles without desk access then becomes a Website User: /app is closed to it (403), /pos, /update-password
and the language menu of the POS keep working. An account that also has the manager role (or any other desk role)
stays a System User. The roles of the accounts are not changed; a Website User just no longer gets Frappe's automatic
"Desk User" role (read on about 45 DocTypes), which the POS does not use.

The Role fixture says the same (it is written back at every migrate, after the patches), so the patch sets the roles
itself first: saving the accounts needs the new values. Accounts are saved with Frappe's own validation, so the
user type comes out of Frappe's rule. Safe to run twice; no commit (migrate commits).
"""

import frappe

ROLES = ("URY Captain", "URY Cashier")


def execute():
	for role in ROLES:
		if frappe.db.exists("Role", role):
			frappe.db.set_value("Role", role, {"desk_access": 0, "home_page": "pos"}, update_modified=False)
	frappe.clear_cache()

	accounts = frappe.get_all(
		"Has Role", filters={"role": ("in", ROLES), "parenttype": "User"}, pluck="parent", distinct=True
	)
	for name in accounts:
		if name in ("Administrator", "Guest"):
			continue
		user = frappe.get_doc("User", name)
		before = user.user_type
		user.save(ignore_permissions=True)
		if before != user.user_type:
			print(f"{name}: {before} -> {user.user_type}")
