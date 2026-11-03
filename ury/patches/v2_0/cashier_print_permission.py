"""The cashier prints the bill (ご請求明細) and the receipt (領収書): give URY Cashier `print` on POS Invoice.

The role had read, write, create, submit and cancel but not print. Printing worked all the same,
because the print view accepts `read` or `print` and URY's own print endpoints check `write`; the
missing permission showed only where `print` is asked for itself (the POS permission check, the
PDF and Desk print menus). Sets that one flag on the existing row of the role and nothing else;
a site without the row (the owner removed it) is left alone. New sites get it from
ury/role_permissions.py.
"""

import frappe

from ury.role_permissions import apply_permissions


def execute():
	row = {"parent": "POS Invoice", "role": "URY Cashier", "permlevel": 0}
	if not (frappe.db.exists("Custom DocPerm", row) or frappe.db.exists("DocPerm", row)):
		return
	apply_permissions("POS Invoice", "URY Cashier", {"permlevel": 0, "print": 1})
	frappe.clear_cache()
