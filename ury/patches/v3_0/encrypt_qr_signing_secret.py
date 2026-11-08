"""Move the signing secret of the QR codes into the encrypted store.

`qr_signing_secret` of the URY Self Ordering Profile was a Data field (plain text in the table, in every backup, and
given by the API to whoever could read the profile). It is a Password field now: encrypted in `__Auth` (with the
encryption_key of the site), only dots in the table. This copies each plain text value to `__Auth` first and
only then replaces it in the table with dots, so the value is never lost and the stickers on the tables stay valid.
Runs again without harm: a profile that has dots or nothing is left alone.
"""

import frappe
from frappe.utils.password import set_encrypted_password

MASK = "*****"


def execute():
	if not frappe.db.has_column("URY Self Ordering Profile", "qr_signing_secret"):
		return
	rows = frappe.db.sql("select name, qr_signing_secret from `tabURY Self Ordering Profile`", as_dict=True)
	for row in rows:
		value = row.qr_signing_secret
		if not value or set(value) == {"*"}:
			continue
		set_encrypted_password("URY Self Ordering Profile", row.name, value, "qr_signing_secret")
		frappe.db.sql("update `tabURY Self Ordering Profile` set qr_signing_secret = %s where name = %s", (MASK, row.name))
	frappe.clear_cache()
