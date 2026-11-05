"""The link in the QR code and the ordering page must agree on where the token is.

The link is `<public url>/order/?<param>=<token>`. The name of the parameter is written once, in
`qr_link.json`: this module builds the link with it and the ordering page (`self-order/src/lib/qr-link.ts`)
reads the token with it. (They once disagreed: the link said `token`, the page read `t`, and every guest
was told the code was missing.) Run on the test site only.
"""

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import frappe

from ury.setup.test_site import URYTestCase
from ury.ury.api.self_ordering import QR_TOKEN_PARAM, generate_qr_token, qr_url

APP = Path(frappe.get_app_path("ury")).parent
SELF_ORDER = APP / "self-order" / "src"


class TestQrLink(URYTestCase):
	def test_the_link_carries_the_token_in_the_parameter_the_page_reads(self):
		link = qr_url("https://order.example.jp", "abc-DEF_123")
		parsed = urlparse(link)
		self.assertEqual((parsed.scheme, parsed.netloc, parsed.path), ("https", "order.example.jp", "/order/"))
		self.assertEqual(parse_qs(parsed.query), {QR_TOKEN_PARAM: ["abc-DEF_123"]})

	def test_a_slash_at_the_end_of_the_address_makes_no_difference(self):
		self.assertEqual(qr_url("https://order.example.jp/", "x"), qr_url("https://order.example.jp", "x"))

	def test_a_real_token_comes_through_the_link_unchanged(self):
		with patch_secret():
			token = generate_qr_token("PROFILE", "T-01")
		link = qr_url("http://ury.localhost:8000", token)
		self.assertEqual(parse_qs(urlparse(link).query)[QR_TOKEN_PARAM], [token])

	def test_the_name_of_the_parameter_is_written_in_one_file_for_both_sides(self):
		param = json.loads((Path(frappe.get_app_path("ury")) / "ury" / "api" / "qr_link.json").read_text())["param"]
		self.assertEqual(QR_TOKEN_PARAM, param)
		self.assertTrue(param and param.isalnum())
		reader = (SELF_ORDER / "lib" / "qr-link.ts").read_text()
		self.assertIn("api/qr_link.json", reader)
		self.assertNotIn(f"'{param}'", reader)  # the page does not write the name again

	def test_the_ordering_hook_reads_the_token_through_that_file_and_not_by_name(self):
		hook = (SELF_ORDER / "hooks" / "useOrderingSession.ts").read_text()
		self.assertIn("tokenFromSearch", hook)
		self.assertNotIn("params.get(", hook)

	def test_a_missing_address_is_refused(self):
		for address in (None, "", "   "):
			with self.assertRaises(frappe.ValidationError):
				qr_url(address, "x")


class patch_secret:
	"""generate_qr_token needs a profile with a secret and the write permission on it."""

	def __enter__(self):
		from unittest.mock import patch

		self.patches = [
			patch("ury.ury.api.self_ordering.frappe.has_permission", return_value=True),
			patch("ury.ury.api.self_ordering.frappe.get_doc"),
			patch("ury.ury.api.self_ordering._get_profile_secret", return_value="a-secret"),
		]
		for p in self.patches:
			p.start()

	def __exit__(self, *exc):
		for p in self.patches:
			p.stop()
