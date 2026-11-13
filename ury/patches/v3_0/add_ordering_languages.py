"""The languages of the customer ordering page: the custom field of the translations on Item, the languages the guests
may choose on every profile (Japanese, Chinese, English), and the languages switched on in the site. The DocTypes
(URY Ordering Language, URY Translation Row, the profile and the session) come from the model sync that runs before
this patch. Safe to run twice; no commit (migrate commits)."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from ury.setup_customizations import get_custom_fields
from ury.ury.doctype.ury_self_ordering_profile.ury_self_ordering_profile import DEFAULT_ORDERING_LANGUAGES


def execute():
	create_custom_fields({"Item": get_custom_fields()["Item"]})

	for language in (*DEFAULT_ORDERING_LANGUAGES, "ko"):
		if frappe.db.exists("Language", language):
			frappe.db.set_value("Language", language, "enabled", 1, update_modified=False)

	for name in frappe.get_all("URY Self Ordering Profile", pluck="name"):
		profile = frappe.get_doc("URY Self Ordering Profile", name)
		if not profile.get("allowed_languages"):
			profile.flags.ignore_permissions = True
			profile.save()  # validate fills the default languages and the default language
	frappe.clear_cache()
