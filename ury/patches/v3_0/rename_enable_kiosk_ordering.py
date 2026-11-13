"""`URY Self Ordering Profile.enable_kiosk_ordering` is `enable_device_ordering` (the label already said so: table tablets and
kiosks are devices). Runs before the DocType is synced: the column is renamed where it is, so the values stay and the
model sync that follows finds the new column. (Frappe's `rename_field` needs the synced DocType, whose new table field
refers to a DocType that is not synced yet at this point.) A site where the new column is already there (a new site, a
second run) is left alone."""

import frappe

TABLE = "URY Self Ordering Profile"


def columns():
	"""The columns as the database has them (Frappe's own list is cached and can be out of date)."""
	return {row[0] for row in frappe.db.sql(f"show columns from `tab{TABLE}`")}


def execute():
	if not frappe.db.table_exists(TABLE):
		return
	found = columns()
	if "enable_kiosk_ordering" in found and "enable_device_ordering" not in found:
		frappe.db.sql_ddl(
			f"alter table `tab{TABLE}` change column `enable_kiosk_ordering` `enable_device_ordering` int(1) not null default 0"
		)
		frappe.cache.hdel("table_columns", f"tab{TABLE}")
