"""The two places that define the custom fields of the standard doctypes agree.

`fixtures/custom_field.json` (exported from the Desk; `migrate` and the install apply it, and it is what the shop's site
has) and `setup_customizations.get_custom_fields()` (what `after_install` and `before_uninstall` use, and the fields
that are not in the fixtures) both describe fields like POS Invoice.restaurant_table. They had drifted apart (2026-11):
a fresh install made the field from the old definition and the fixtures then changed it again, and running the
install steps again on an existing site wrote the old definition over the field (an arrived_time that is a Time in
one place and Data in the other). For the fields that are in both, every property must be the same. Read only.
"""

import json

import frappe

from ury.setup.test_site import URYTestCase

PROPERTIES = (
	"fieldtype", "options", "read_only", "hidden", "insert_after", "default", "label", "reqd", "fetch_from", "depends_on",
	"allow_on_submit", "translatable", "fetch_if_empty", "in_list_view", "in_standard_filter", "bold", "collapsible",
	"unique", "print_hide", "no_copy", "permlevel", "description", "precision", "length",
)


def blank(value):
	return None if value in (None, "", 0, "0") else str(value)


def fixtures():
	with open(frappe.get_app_path("ury", "fixtures", "custom_field.json"), encoding="utf-8") as f:
		return {(row["dt"], row["fieldname"]): row for row in json.load(f)}


class TestCustomFieldsAgree(URYTestCase):
	def differences(self):
		from ury.setup_customizations import get_custom_fields

		shared = fixtures()
		found = []
		for doctype, fields in get_custom_fields().items():
			for definition in fields:
				fixture = shared.get((doctype, definition["fieldname"]))
				if not fixture:
					continue
				for prop in PROPERTIES:
					if blank(definition.get(prop)) != blank(fixture.get(prop)):
						found.append(f"{doctype}.{definition['fieldname']}.{prop}: get_custom_fields {definition.get(prop)!r}, fixtures {fixture.get(prop)!r}")
		return found

	def test_every_property_of_a_field_in_both_places_is_the_same(self):
		self.assertEqual(self.differences(), [])

	def test_the_fields_that_are_only_in_the_code_are_known(self):
		from ury.setup_customizations import get_custom_fields

		shared = fixtures()
		only_code = sorted(
			f"{dt}.{d['fieldname']}" for dt, fields in get_custom_fields().items() for d in fields if (dt, d["fieldname"]) not in shared
		)
		# fields the install makes that the fixtures do not carry (self ordering, the tax rounding ...): a new one is
		# a choice to be made on purpose, so the list is written out here
		self.assertEqual(
			only_code,
			sorted(
				[
					"Item.custom_translations", "POS Invoice.column_break_selford", "POS Invoice.custom_order_source", "POS Invoice.custom_ordering_device",
					"POS Invoice.custom_ordering_session", "POS Invoice.self_ordering_info", "POS Profile.custom_tax_rounding",
					"Sales Invoice.column_break_gd1mq", "Sales Invoice.column_break_rwbwf", "URY KOT.custom_merged_tables",
				]
			),
		)
