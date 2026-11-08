"""The patch that renames `last_seen` to `last_reported_at` (URY Ordering Device, URY Payment Terminal).

Frappe leaves a field with `_seen` in its name out of the list queries (docs/frappe-optional-columns.md). The patch copies
the values to the new column and drops the old one; it can run again. Run on the test site only.
"""

import frappe

from ury.setup.test_site import URYFlowTestCase

DOCTYPES = ("URY Ordering Device", "URY Payment Terminal")


def has_column(doctype, column):
	return bool(frappe.db.sql(f"show columns from `tab{doctype}` like %s", column))


def execute():
	from ury.patches.v3_0.rename_last_seen import execute as run

	run()
	frappe.db.commit()


class TestRenameLastSeen(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(self._drop_old_columns)
		self.name = "rename-test-" + frappe.generate_hash(length=6)
		for doctype in DOCTYPES:
			frappe.db.sql_ddl(f"alter table `tab{doctype}` add column if not exists `last_seen` datetime(6)")
		frappe.db.sql(
			"insert into `tabURY Payment Terminal` (name, creation, modified, modified_by, owner, docstatus, idx, terminal_id, last_seen) "
			"values (%s, now(), now(), 'Administrator', 'Administrator', 0, 0, %s, '2026-11-08 05:00:00.123456')",
			(self.name, self.name),
		)
		frappe.db.sql(
			"insert into `tabURY Ordering Device` (name, creation, modified, modified_by, owner, docstatus, idx, device_id, last_seen) "
			"values (%s, now(), now(), 'Administrator', 'Administrator', 0, 0, %s, '2026-11-08 05:01:00.654321')",
			(self.name, self.name),
		)
		frappe.db.commit()

	def _drop_old_columns(self):
		for doctype in DOCTYPES:
			frappe.db.delete(doctype, {"name": self.name})
			if has_column(doctype, "last_seen"):
				frappe.db.sql_ddl(f"alter table `tab{doctype}` drop column `last_seen`")
		frappe.db.commit()

	def test_the_values_are_kept_in_the_new_column_and_the_old_one_is_gone(self):
		execute()
		for doctype, expected in (("URY Payment Terminal", "2026-11-08 05:00:00.123456"), ("URY Ordering Device", "2026-11-08 05:01:00.654321")):
			self.assertFalse(has_column(doctype, "last_seen"), doctype)
			self.assertEqual(str(frappe.db.get_value(doctype, self.name, "last_reported_at")), expected, doctype)

	def test_it_can_run_again_and_a_newer_value_is_not_overwritten(self):
		execute()
		frappe.db.set_value("URY Ordering Device", self.name, "last_reported_at", "2026-11-09 10:00:00")
		execute()
		self.assertEqual(str(frappe.db.get_value("URY Ordering Device", self.name, "last_reported_at")), "2026-11-09 10:00:00")
