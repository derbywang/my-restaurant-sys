"""The language of the customer ordering page.

The guest's language is kept on the ordering session (`URY Ordering Session.language`), chosen from the languages the
profile allows (`allowed_languages`, the default language always among them). The server answers in it: the names of
the dishes and of the courses come from translation rows (`URY Translation Row`), the standard name (the Japanese
`item_name`) is shown where there is no row. The language reaches nothing else: not the order, the kitchen, the bill,
the staff screens, any user record or cookie. A language added later (e.g. `zh-TW`) is a Language, a language pack for
the page and rows: nothing here depends on the list of languages.
"""

import frappe

# how a language is written in its own language (the Language document of Frappe has odd names, e.g. 한국의)
NATIVE_LABELS = {"ja": "日本語", "zh": "中文", "ko": "한국어", "en": "English"}
FALLBACK_LANGUAGE = "ja"


def allowed_languages(profile):
	"""The language codes the guests can choose, in the order of the profile."""
	return [row.language for row in profile.get("allowed_languages") if row.language]


def default_language(profile):
	return profile.default_language or FALLBACK_LANGUAGE


def language_options(profile):
	options = []
	for code in allowed_languages(profile):
		label = NATIVE_LABELS.get(code) or frappe.db.get_value("Language", code, "language_name") or code
		options.append({"code": code, "label": label})
	return options


def session_language(session, profile):
	"""The language of a session; one that is no longer allowed (the profile changed) falls back to the default."""
	language = session.get("language")
	return language if language in allowed_languages(profile) else default_language(profile)


def _labels(parenttype, parentfield, parents, language):
	if not parents or not language or not isinstance(language, str):
		return {}
	rows = frappe.get_all(
		"URY Translation Row",
		filters={"parenttype": parenttype, "parentfield": parentfield, "parent": ("in", list(parents)), "language": language},
		fields=["parent", "label"],
	)
	return {row.parent: row.label.strip() for row in rows if row.label and row.label.strip()}


def item_names(item_codes, language):
	"""{item code: the name in `language`} for the items that have one."""
	return _labels("Item", "custom_translations", item_codes, language)


def course_names(courses, language):
	"""{course: the name in `language`} for the courses that have one."""
	return _labels("URY Menu Course", "translations", courses, language)
