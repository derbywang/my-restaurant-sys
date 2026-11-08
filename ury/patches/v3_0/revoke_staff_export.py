"""The captain and the cashier cannot export anything.

`export` lets a user download a whole list (every bill with its totals, every customer, every user) as a file from
the Desk. Neither the POS nor the work of these two roles needs it: bills are printed (`print`), the shift is closed
in the POS Closing Entry. `ury/role_permissions.py` never wrote the flag, so Frappe's default (1) applied on most
DocTypes. This clears it on every permission row of URY Captain and URY Cashier, Custom DocPerm and standard
DocPerm alike (the DocType files of the URY DocTypes say 0 too, so a later sync keeps it). The manager and the
admin are not touched. New sites get the same from role_permissions.py ("export": 0 on every entry).

Plain updates, no commit (migrate commits); safe to run twice.
"""

import frappe

ROLES = ("URY Captain", "URY Cashier")


def execute():
	for table in ("Custom DocPerm", "DocPerm"):
		frappe.db.sql(f"update `tab{table}` set `export` = 0 where role in %(roles)s and `export` != 0", {"roles": ROLES})
	frappe.clear_cache()
