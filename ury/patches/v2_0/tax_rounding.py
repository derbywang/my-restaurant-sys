import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from ury.setup_customizations import get_custom_fields


def execute():
	"""POS Profile.custom_tax_rounding, set to the default (round down) everywhere."""
	fields = [f for f in get_custom_fields()["POS Profile"] if f["fieldname"] == "custom_tax_rounding"]
	create_custom_fields({"POS Profile": fields})
	frappe.db.sql(
		"update `tabPOS Profile` set custom_tax_rounding = 'Round Down' where ifnull(custom_tax_rounding, '') = ''"
	)
