"""The language of the customer ordering page (2026-11-14): Japanese, Chinese (simplified, `zh`), Korean, English.

The language belongs to the ordering session (`URY Ordering Session.language`): the guest chooses it on the page, the
server answers in it. It never reaches the order, the kitchen, the staff screens or the user records, and a new
session (the staff open the table again, a kiosk resets) starts in the profile's default language. The names of the
dishes and of the courses come from translation rows; without one the standard (Japanese) name is shown.
Adding another language later (e.g. Traditional Chinese, `zh-TW`) needs a language pack and translation rows, no
change of structure. Run on the test site only (a trial site first)."""

import frappe

from ury.setup.test_site import CASHIER, FOOD_COURSE, FOOD_ITEM
from ury.ury.api.self_ordering import (
	add_customer_items,
	get_customer_menu,
	get_customer_order,
	get_customer_product,
	get_ordering_context,
	generate_qr_token,
	set_session_language,
)
from ury.ury.api.test_self_ordering_table import PROFILE, TABLE, SelfOrderingCase


def add_translation(parent, parenttype, parentfield, language, label):
	frappe.get_doc(
		{"doctype": "URY Translation Row", "parent": parent, "parenttype": parenttype, "parentfield": parentfield,
		 "language": language, "label": label}
	).db_insert()


class LanguageCase(SelfOrderingCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(self._remove_translations)
		self._remove_translations()
		self.staff_open()
		self.standard_name = frappe.db.get_value("Item", FOOD_ITEM, "item_name")

	def _remove_translations(self):
		frappe.db.delete("URY Translation Row", {"parent": ("in", (FOOD_ITEM, FOOD_COURSE))})

	def context(self, table=TABLE):
		from ury.setup.test_site import as_user

		with as_user("Administrator"):
			token = generate_qr_token(PROFILE, table)
		return get_ordering_context(token=token)

	def menu_row(self, session):
		return [row for row in get_customer_menu(session)["items"] if row["item"] == FOOD_ITEM][0]


class TestTheLanguagesOfAProfile(LanguageCase):
	def codes(self):
		profile = frappe.get_doc("URY Self Ordering Profile", PROFILE)
		return [row.language for row in profile.get("allowed_languages")]

	def test_a_new_profile_allows_japanese_chinese_and_english(self):
		self.assertEqual(self.codes(), ["ja", "zh", "en"])

	def test_the_default_language_is_always_allowed(self):
		profile = frappe.get_doc("URY Self Ordering Profile", PROFILE)
		profile.default_language = "ko"
		profile.save(ignore_permissions=True)
		self.assertIn("ko", self.codes())

	def test_the_context_names_the_languages_and_the_session_starts_in_the_default(self):
		context = self.context()
		self.assertEqual(context["language"], "ja")
		self.assertEqual([row["code"] for row in context["languages"]], ["ja", "zh", "en"])
		self.assertEqual([row["label"] for row in context["languages"]], ["日本語", "中文", "English"])

	def test_the_session_keeps_its_language(self):
		session = self.context()["session"]
		self.assertEqual(frappe.db.get_value("URY Ordering Session", {"ordering_profile": PROFILE}, "language"), "ja")
		self.assertEqual(set_session_language(session, "zh")["language"], "zh")
		self.assertEqual(frappe.db.get_value("URY Ordering Session", {"ordering_profile": PROFILE}, "language"), "zh")

	def test_a_language_the_profile_does_not_allow_is_refused(self):
		session = self.context()["session"]
		with self.assertRaises(frappe.ValidationError):
			set_session_language(session, "ko")  # korean waits for the proofreading
		with self.assertRaises(frappe.ValidationError):
			set_session_language(session, "xx")
		self.assertEqual(frappe.db.get_value("URY Ordering Session", {"ordering_profile": PROFILE}, "language"), "ja")


class TestTheNamesInTheGuestsLanguage(LanguageCase):
	def setUp(self):
		super().setUp()
		add_translation(FOOD_ITEM, "Item", "custom_translations", "zh", "寿司测试")
		add_translation(FOOD_ITEM, "Item", "custom_translations", "en", "Test sushi")
		add_translation(FOOD_COURSE, "URY Menu Course", "translations", "zh", "主菜")
		self.session = self.context()["session"]

	def test_in_japanese_the_standard_name_is_shown(self):
		self.assertEqual(self.menu_row(self.session)["item_name"], self.standard_name)

	def test_in_chinese_the_translated_name_and_course(self):
		set_session_language(self.session, "zh")
		row = self.menu_row(self.session)
		self.assertEqual(row["item_name"], "寿司测试")
		self.assertEqual(row["course_label"], "主菜")

	def test_a_language_without_a_translation_shows_the_standard_name(self):
		frappe.db.delete("URY Translation Row", {"parent": FOOD_ITEM, "language": "en"})
		set_session_language(self.session, "en")
		self.assertEqual(self.menu_row(self.session)["item_name"], self.standard_name)

	def test_a_blank_translation_shows_the_standard_name(self):
		frappe.db.set_value("URY Translation Row", {"parent": FOOD_ITEM, "language": "zh"}, "label", "  ")
		set_session_language(self.session, "zh")
		self.assertEqual(self.menu_row(self.session)["item_name"], self.standard_name)

	def test_the_product_page_and_the_order_use_the_language(self):
		set_session_language(self.session, "zh")
		self.assertEqual(get_customer_product(self.session, FOOD_ITEM)["item_name"], "寿司测试")
		add_customer_items(self.session, [{"item": FOOD_ITEM, "qty": 1}])
		order = get_customer_order(self.session)
		self.assertEqual([row["item_name"] for row in order["items"]], ["寿司测试"])

	def test_the_order_the_kitchen_and_the_bill_keep_the_standard_name(self):
		set_session_language(self.session, "zh")
		add_customer_items(self.session, [{"item": FOOD_ITEM, "qty": 1}])
		invoice = get_customer_order(self.session)["invoice"]
		self.assertEqual(
			frappe.get_all("POS Invoice Item", filters={"parent": invoice}, pluck="item_name"), [self.standard_name]
		)
		tickets = frappe.get_all("URY KOT", filters={"invoice": invoice}, pluck="name")
		self.assertTrue(tickets)
		self.assertEqual(
			set(frappe.get_all("URY KOT Items", filters={"parent": ("in", tickets)}, pluck="item_name")),
			{self.standard_name},
		)


class TestWhoIsAffected(LanguageCase):
	def test_a_new_session_starts_in_the_default_language(self):
		first = self.context()["session"]
		set_session_language(first, "zh")
		second = self.context()  # the staff opened the table again, a kiosk reset: a new session
		self.assertEqual(second["language"], "ja")
		self.assertEqual(self.menu_row(second["session"])["item_name"], self.standard_name)

	def test_the_choice_changes_no_user_and_no_cookie_and_not_the_language_of_the_request(self):
		before = {u: frappe.db.get_value("User", u, "language") for u in ("Administrator", CASHIER)}
		lang = frappe.local.lang
		session = self.context()["session"]
		set_session_language(session, "zh")
		self.menu_row(session)
		self.assertEqual({u: frappe.db.get_value("User", u, "language") for u in before}, before)
		self.assertEqual(frappe.local.lang, lang)
		cookies = getattr(getattr(frappe.local, "cookie_manager", None), "cookies", {}) or {}
		self.assertNotIn("preferred_language", cookies)


class TestAnotherLanguageLater(LanguageCase):
	"""Traditional Chinese (`zh-TW`) is added without changing a structure: a Language, a language pack, rows."""

	def test_a_new_language_is_a_row_of_the_profile_and_translation_rows(self):
		enabled = frappe.db.get_value("Language", "zh-TW", "enabled")
		self.addCleanup(frappe.db.set_value, "Language", "zh-TW", "enabled", enabled)
		frappe.db.set_value("Language", "zh-TW", "enabled", 1)
		profile = frappe.get_doc("URY Self Ordering Profile", PROFILE)
		profile.append("allowed_languages", {"language": "zh-TW"})
		profile.save(ignore_permissions=True)
		add_translation(FOOD_ITEM, "Item", "custom_translations", "zh-TW", "壽司測試")
		context = self.context()
		self.assertIn("zh-TW", [row["code"] for row in context["languages"]])
		self.assertEqual(
			[row["label"] for row in context["languages"] if row["code"] == "zh-TW"], ["繁體中文"]
		)
		set_session_language(context["session"], "zh-TW")
		self.assertEqual(self.menu_row(context["session"])["item_name"], "壽司測試")


class TestThePatch(LanguageCase):
	def test_a_profile_without_languages_gets_the_defaults_and_running_twice_changes_nothing(self):
		from ury.patches.v3_0.add_ordering_languages import execute

		frappe.db.delete("URY Ordering Language", {"parent": PROFILE})
		execute()
		profile = frappe.get_doc("URY Self Ordering Profile", PROFILE)
		self.assertEqual([row.language for row in profile.allowed_languages], ["ja", "zh", "en"])
		execute()
		profile = frappe.get_doc("URY Self Ordering Profile", PROFILE)
		self.assertEqual([row.language for row in profile.allowed_languages], ["ja", "zh", "en"])


class TestTheRenamePatch(LanguageCase):
	"""enable_kiosk_ordering -> enable_device_ordering keeps the values (a shop with tablets has it at 1).
	The column is renamed back for the test and always put right again."""

	TABLE = "URY Self Ordering Profile"

	def _rename(self, old, new):
		frappe.db.sql_ddl(f"alter table `tab{self.TABLE}` change column `{old}` `{new}` int(1) not null default 0")
		frappe.cache.hdel("table_columns", f"tab{self.TABLE}")

	def _restore(self):
		from ury.patches.v3_0.rename_enable_kiosk_ordering import columns

		if "enable_kiosk_ordering" in columns() and "enable_device_ordering" not in columns():
			self._rename("enable_kiosk_ordering", "enable_device_ordering")

	def test_the_value_stays_and_a_second_run_changes_nothing(self):
		from ury.patches.v3_0.rename_enable_kiosk_ordering import columns, execute

		frappe.db.set_value(self.TABLE, PROFILE, "enable_device_ordering", 1)
		frappe.db.commit()
		self.addCleanup(self._restore)
		self._rename("enable_device_ordering", "enable_kiosk_ordering")
		execute()
		self.assertIn("enable_device_ordering", columns())
		self.assertNotIn("enable_kiosk_ordering", columns())
		self.assertEqual(frappe.db.get_value(self.TABLE, PROFILE, "enable_device_ordering"), 1)
		execute()  # nothing to do the second time
		self.assertEqual(frappe.db.get_value(self.TABLE, PROFILE, "enable_device_ordering"), 1)
