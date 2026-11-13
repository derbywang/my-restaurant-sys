"""The role URY Kitchen: the account of a kitchen screen (/mosaic).

It reads and serves the kitchen tickets (URY KOT: read, write) and reads the production units; no Desk, its home page is
the kitchen screen. The Role fixture and the DocType files say the same (written at migrate: the fixture after the
patches, the DocType permissions in the model sync), so this patch only makes sure that

* the Role exists before anything refers to it (a patch that runs before the fixture sync cannot link to it), and
* a site whose URY KOT or URY Production Unit has Custom DocPerm rows (Frappe then ignores the DocType file) gets the
  two permission rows too.

Safe to run twice; no commit (migrate commits).
"""

import frappe

from ury.role_permissions import apply_permissions

ROLE = "URY Kitchen"
PERMISSIONS = (
	("URY KOT", {"permlevel": 0, "select": 1, "read": 1, "write": 1, "export": 0}),
	("URY Production Unit", {"permlevel": 0, "select": 1, "read": 1, "export": 0}),
)


def execute():
	if not frappe.db.exists("Role", ROLE):
		frappe.get_doc(
			{"doctype": "Role", "role_name": ROLE, "desk_access": 0, "home_page": "mosaic", "is_custom": 0}
		).insert(ignore_permissions=True)
	else:
		frappe.db.set_value("Role", ROLE, {"desk_access": 0, "home_page": "mosaic"}, update_modified=False)

	for doctype, perms in PERMISSIONS:
		if frappe.db.exists("Custom DocPerm", {"parent": doctype}):
			apply_permissions(doctype, ROLE, perms)
	frappe.clear_cache()
