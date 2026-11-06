"""The page with the QR codes for the tables (self-order-design 3.9). Run on the test site only."""

from urllib.parse import parse_qs, urlparse

import frappe

from ury.setup.test_site import CAPTAIN, TABLES, as_user
from ury.ury.api.qr_print import table_codes, table_qr_print_html
from ury.ury.api.self_ordering import QR_TOKEN_PARAM, _verify_qr_token
from ury.ury.api.test_self_ordering_table import PROFILE, SelfOrderingCase

PUBLIC_URL = "https://order.example.jp"


class TestTableQrPrint(SelfOrderingCase):
	def setUp(self):
		super().setUp()
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, "public_url", PUBLIC_URL)

	def test_every_dine_in_table_gets_a_code_with_the_public_address(self):
		codes = table_codes(PROFILE)
		self.assertEqual([code["table"] for code in codes], sorted(TABLES))
		for code in codes:
			self.assertTrue(code["url"].startswith(f"{PUBLIC_URL}/order/?{QR_TOKEN_PARAM}="))
			self.assertIn("<svg", code["svg"])

	def test_the_token_of_a_code_opens_that_table(self):
		for code in table_codes(PROFILE):
			token = parse_qs(urlparse(code["url"]).query)[QR_TOKEN_PARAM][0]
			_profile, table, source = _verify_qr_token(token)
			self.assertEqual((table, source), (code["table"], "QR Table"))

	def test_the_address_of_the_request_is_never_written_in_the_codes(self):
		from werkzeug.test import EnvironBuilder
		from werkzeug.wrappers import Request

		previous = getattr(frappe.local, "request", None)
		frappe.local.request = Request(EnvironBuilder(base_url="http://192.168.0.10:8000").get_environ())
		self.addCleanup(lambda: setattr(frappe.local, "request", previous))
		html = table_qr_print_html(PROFILE)
		for code in table_codes(PROFILE):
			self.assertNotIn("192.168.0.10", code["url"])
		self.assertNotIn("192.168.0.10", html)

	def test_without_the_public_address_nothing_is_printed(self):
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, "public_url", None)
		with self.assertRaises(frappe.ValidationError):
			table_qr_print_html(PROFILE)

	def test_the_page_has_a_code_a_name_and_the_sentence_for_each_table(self):
		html = table_qr_print_html(PROFILE)
		self.assertEqual(html.count("<svg"), len(TABLES))
		for table in TABLES:
			self.assertIn(f'<div class="table">{table}</div>', html)
		self.assertEqual(html.count('class="sentence"'), len(TABLES))

	def test_the_sentence_is_in_the_language_of_the_profile_not_of_the_system(self):
		language = frappe.db.get_single_value("System Settings", "language")
		self.addCleanup(self._set_language, language)
		self._set_language("en")  # the system (and so the staff) speak English; the shop's guests Japanese
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, "default_language", "ja")
		html = table_qr_print_html(PROFILE)
		self.assertIn("QRコードを読み取ってご注文ください", html)
		self.assertNotIn("Scan the QR code", html)

	def test_the_user_language_of_the_staff_makes_no_difference_either(self):
		previous = frappe.local.lang
		self.addCleanup(lambda: setattr(frappe.local, "lang", previous))
		frappe.local.lang = "en"
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, "default_language", "ja")
		self.assertIn("QRコードを読み取ってご注文ください", table_qr_print_html(PROFILE))

	def test_a_profile_may_choose_another_language(self):
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, "default_language", "en")
		self.assertIn("Scan the QR code to place your order", table_qr_print_html(PROFILE))

	def test_a_profile_without_a_language_prints_japanese(self):
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, "default_language", None)
		self.assertIn("QRコードを読み取ってご注文ください", table_qr_print_html(PROFILE))

	def test_a_new_profile_starts_with_japanese(self):
		self.assertEqual(frappe.get_meta("URY Self Ordering Profile").get_field("default_language").default, "ja")

	def test_the_message_of_the_button_is_translated(self):
		from frappe.translate import get_all_translations

		messages = get_all_translations("ja")
		self.assertIn("Set the Public URL first: it is written in the QR codes.", messages)
		self.assertIn("Print table QR codes", messages)


	def test_the_page_is_a4_with_six_cards_to_a_page(self):
		html = table_qr_print_html(PROFILE)
		self.assertIn("size: A4", html)
		self.assertIn("grid-template-columns: 1fr 1fr", html)
		self.assertIn("grid-auto-rows: 88mm", html)  # 3 rows of 88 mm in the 277 mm of an A4 page
		self.assertIn(".card:nth-child(6n) { break-after: page; }", html)

	def test_the_take_away_counter_gets_no_code(self):
		frappe.db.set_value("URY Table", TABLES[2], "is_take_away", 1)
		self.addCleanup(lambda: frappe.db.set_value("URY Table", TABLES[2], "is_take_away", 0))
		self.assertEqual([code["table"] for code in table_codes(PROFILE)], sorted(TABLES[:2]))

	def test_someone_who_may_not_change_the_profile_cannot_print(self):
		with as_user(CAPTAIN), self.assertRaises(frappe.PermissionError):
			table_qr_print_html(PROFILE)

	def _set_language(self, language):
		frappe.db.set_single_value("System Settings", "language", language)
		frappe.clear_cache()


class TestPublicUrlField(SelfOrderingCase):
	def _save(self, value):
		doc = frappe.get_doc("URY Self Ordering Profile", PROFILE)
		doc.public_url = value
		doc.save(ignore_permissions=True)
		return doc.public_url

	def test_a_slash_at_the_end_is_dropped(self):
		self.assertEqual(self._save("https://order.example.jp/"), PUBLIC_URL)

	def test_a_port_is_allowed(self):
		self.assertEqual(self._save("http://ury.localhost:8000"), "http://ury.localhost:8000")

	def test_empty_is_allowed(self):
		self.assertIsNone(self._save("   "))

	def test_a_path_or_a_wrong_scheme_is_refused(self):
		for value in ("https://order.example.jp/shop", "ftp://order.example.jp", "order.example.jp"):
			with self.assertRaises(frappe.ValidationError):
				self._save(value)
