"""The pages of the apps and the ordering calls are never cached (docs/design/self-order-design.md, 9.2).

The HTML of /order carries the CSRF token and names the JS files of the current build, so a copy kept by a browser or
by Cloudflare would be wrong. `no_cache = 1` in the page modules does not set an HTTP header, so a hook does.
Static files under /assets have names with a hash and are left to their own long caching.
"""

import unittest

from werkzeug.wrappers import Response

from ury.ury.api.cache_headers import NO_STORE, after_request


class FakeRequest:
	def __init__(self, path):
		self.path = path


def headers_for(path, **headers):
	response = Response("x", headers=headers)
	after_request(response=response, request=FakeRequest(path))
	return response.headers


class TestNoStore(unittest.TestCase):
	def assert_no_store(self, path):
		self.assertEqual(headers_for(path).get("Cache-Control"), NO_STORE, path)

	def assert_untouched(self, path):
		self.assertIsNone(headers_for(path).get("Cache-Control"), path)

	def test_the_ordering_page_and_everything_below_it(self):
		for path in ("/order", "/order/", "/order/anything", "/order/setup"):
			self.assert_no_store(path)

	def test_the_pages_of_the_other_apps(self):
		for path in ("/pos", "/pos/", "/pos/tables", "/mosaic/Kitchen", "/mosaic", "/ury", "/ury/setup-wizard/0"):
			self.assert_no_store(path)

	def test_the_calls_of_the_ordering_page(self):
		for name in ("get_customer_menu", "get_customer_order", "preview_customer_cart", "add_customer_items", "confirm_age"):
			self.assert_no_store(f"/api/method/ury.ury.api.self_ordering.{name}")

	def test_the_files_of_the_build_are_left_alone(self):
		for path in ("/assets/ury/order/assets/index-B-BjKm0u.js", "/assets/ury/pos/assets/index-1.css", "/assets/frappe/js/frappe.js"):
			self.assert_untouched(path)

	def test_other_calls_and_pages_are_left_alone(self):
		for path in ("/api/method/ury.ury_pos.api.getRestaurantMenu", "/api/resource/Item", "/app/item", "/login", "/files/a.png"):
			self.assert_untouched(path)

	def test_a_name_that_only_starts_like_a_page_is_not_one(self):
		for path in ("/ordering", "/posts", "/mosaics", "/uryx", "/pos.png", "/assets/order/x.js"):
			self.assert_untouched(path)

	def test_the_query_string_is_not_part_of_the_path(self):
		# the request's path never holds the query string; the hook goes by the path alone
		self.assert_no_store("/order/")

	def test_an_earlier_header_is_replaced(self):
		self.assertEqual(headers_for("/order/", **{"Cache-Control": "max-age=3600"}).get("Cache-Control"), NO_STORE)

	def test_the_response_is_returned_and_nothing_else_changes(self):
		response = Response("body", headers={"X-Test": "1"})
		after_request(response=response, request=FakeRequest("/order/"))
		self.assertEqual(response.get_data(as_text=True), "body")
		self.assertEqual(response.headers.get("X-Test"), "1")

	def test_a_request_without_a_path_does_not_break_the_hook(self):
		response = Response("x")
		after_request(response=response, request=object())
		self.assertIsNone(response.headers.get("Cache-Control"))

	def test_it_is_registered_as_an_after_request_hook(self):
		from ury import hooks

		self.assertIn("ury.ury.api.cache_headers.after_request", hooks.after_request)
