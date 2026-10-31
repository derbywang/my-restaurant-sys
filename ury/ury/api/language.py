import frappe
from frappe import _

# Languages offered in the staff language menu. Codes are Frappe Language names.
STAFF_LANGUAGES = [
	{"code": "ja", "label": "日本語"},
	{"code": "zh", "label": "中文"},
	{"code": "ko", "label": "한국어"},
	{"code": "en", "label": "English"},
]

# Single source of truth for the allowed codes (also used by on_session_creation
# and the staff_language_settings patch).
STAFF_LANGUAGE_CODES = tuple(option["code"] for option in STAFF_LANGUAGES)


@frappe.whitelist()
def get_language_options():
	return STAFF_LANGUAGES


@frappe.whitelist()
def set_staff_language(lang):
	"""Set the language of the logged-in user only; callers cannot target another user."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Please log in to change the language"), frappe.PermissionError)

	if lang not in STAFF_LANGUAGE_CODES:
		frappe.throw(_("Unsupported language: {0}").format(lang), frappe.ValidationError)

	frappe.db.set_value("User", user, "language", lang)
	frappe.clear_cache(user=user)
	return lang
