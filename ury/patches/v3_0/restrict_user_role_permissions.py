"""Take away the rights that let the staff make themselves, or others, more powerful.

URY Captain and URY Cashier could write permission level 1 of the User (roles, user_type, api_key): with the right
every account has on its own User they could add System Manager to themselves. URY Manager wrote the User, Role,
Role Profile and Module Profile, URY Admin the last three (and the User, which the hook in ury/user_security.py now
keeps off the accounts of the System Managers). Clears those flags on the rows that exist; a site without the row
(the owner removed it) is left alone. New sites get the same from ury/role_permissions.py.
"""

import frappe
from frappe.permissions import update_permission_property

from ury.role_permissions import REVOKED


def execute():
	for doctype, role, permlevel, ptypes in REVOKED:
		row = {"parent": doctype, "role": role, "permlevel": permlevel}
		if not (frappe.db.exists("Custom DocPerm", row) or frappe.db.exists("DocPerm", row)):
			continue
		for ptype in ptypes:
			update_permission_property(doctype, role, permlevel, ptype, 0, validate=False)
	frappe.clear_cache()
