"""`last_seen` is now `last_reported_at` (URY Ordering Device, URY Payment Terminal).

Frappe leaves a field with `_seen` in its name out of every list query (`set_optional_columns` in frappe/model/db_query.py
matches the name of the optional column `_seen` as a substring): the Desk list of the devices never got `last_seen` and
showed every tablet as silent. The DocType sync has added the new column; this copies the values and drops the old column.
Runs again without harm (nothing to do once the old column is gone; a newer value is not overwritten).
See docs/frappe-optional-columns.md.
"""

import frappe

DOCTYPES = ("URY Ordering Device", "URY Payment Terminal")


def _has_column(doctype, column):
	"""Asked of the database itself (`has_column` answers from a cache that a column dropped or added here does not refresh)."""
	return bool(frappe.db.sql(f"show columns from `tab{doctype}` like %s", column))


def execute():
	for doctype in DOCTYPES:
		if not _has_column(doctype, "last_seen") or not _has_column(doctype, "last_reported_at"):
			continue
		frappe.db.sql(
			f"update `tab{doctype}` set `last_reported_at` = `last_seen` "
			"where `last_seen` is not null and `last_reported_at` is null"
		)
		frappe.db.sql_ddl(f"alter table `tab{doctype}` drop column `last_seen`")
	frappe.clear_cache()
