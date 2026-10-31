import frappe

from ury.ury.api.language import STAFF_LANGUAGE_CODES


def execute():
	apply_staff_language_settings()


def apply_staff_language_settings():
	"""Show the language picker on the login page and offer only the staff languages.

	Idempotent. Also called from after_install, because installing an app marks
	every patch as already run without executing it. System Settings' default
	language is deliberately left to each store.
	"""
	frappe.db.set_single_value("Website Settings", "show_language_picker", 1)

	for name, enabled in frappe.get_all("Language", fields=["name", "enabled"], as_list=True):
		wanted = int(name in STAFF_LANGUAGE_CODES)
		if enabled != wanted:
			frappe.db.set_value("Language", name, "enabled", wanted, update_modified=False)

	frappe.cache.delete_value(["languages", "languages_with_name"])
	frappe.clear_cache()
