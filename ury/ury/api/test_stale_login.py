"""The logins of an account that is deleted or disabled end with it; a login that is left over is treated as "not logged in".

Why: an account deleted by a script (not through the Desk) kept its login, and the tablet that still had it open showed
a page full of English errors (DoesNotExistError: User ... not found, 2026-11-14). The shop will delete the accounts of
people who leave. Two layers, both tested here:

  1. deleting or disabling an account clears every login of it, whoever does it (a script has no login manager);
  2. a login of an account that no longer exists is dropped at the start of the request: the page is the login page.

The HTTP tests ask the running server (port 8000), as the tablet and the browser do: a GET is rolled back at its end
unless the code commits, which a call in Python cannot show.
"""

import http.client
import re
import urllib.parse

import frappe
from frappe.utils.password import update_password

from ury.setup.test_site import URYTestCase

USER = "stale-login-test@example.com"
PASSWORD = "Stale-Login-2026-xK9!"


def _remove_user():
	frappe.db.rollback()
	frappe.db.delete("Sessions", {"user": USER})
	if frappe.db.exists("User", USER):
		frappe.delete_doc("User", USER, force=True, ignore_permissions=True)
	frappe.db.delete("Sessions", {"user": USER})
	frappe.db.commit()
	frappe.clear_cache(user=USER)


def _make_user(enabled=1):
	frappe.get_doc(
		{"doctype": "User", "email": USER, "first_name": "Stale", "send_welcome_email": 0, "enabled": enabled,
		 "roles": [{"role": "URY Captain"}]}
	).insert(ignore_permissions=True)
	update_password(USER, PASSWORD)
	frappe.db.commit()


def _a_login_row(sid):
	frappe.db.sql(
		"insert into tabSessions (sid, user, lastupdate, sessiondata, ipaddress, status) values (%s, %s, now(6), %s, %s, %s)",
		(sid, USER, "{}", "127.0.0.1", "Active"),
	)
	frappe.db.commit()


def _logins():
	frappe.db.rollback()  # see what has been committed
	return [row[0] for row in frappe.db.sql("select sid from tabSessions where user = %s order by sid", USER)]


class TestTheLoginsEndWithTheAccount(URYTestCase):
	def setUp(self):
		super().setUp()
		_remove_user()
		self.addCleanup(_remove_user)
		_make_user()

	def test_deleting_the_account_ends_its_logins(self):
		_a_login_row("stale-test-sid-1")
		_a_login_row("stale-test-sid-2")
		frappe.delete_doc("User", USER, force=True, ignore_permissions=True)
		frappe.db.commit()
		self.assertEqual(_logins(), [])

	def test_disabling_the_account_ends_its_logins(self):
		_a_login_row("stale-test-sid-1")
		user = frappe.get_doc("User", USER)
		user.enabled = 0
		user.save(ignore_permissions=True)
		frappe.db.commit()
		self.assertEqual(_logins(), [])

	def test_changing_something_else_keeps_the_logins(self):
		_a_login_row("stale-test-sid-1")
		user = frappe.get_doc("User", USER)
		user.first_name = "Another"
		user.save(ignore_permissions=True)
		frappe.db.commit()
		self.assertEqual(_logins(), ["stale-test-sid-1"])

	def test_the_logins_of_the_other_accounts_stay(self):
		def others():
			frappe.db.rollback()
			return frappe.db.sql("select count(*) from tabSessions where user != %s", USER)[0][0]

		before = others()
		_a_login_row("stale-test-sid-1")
		frappe.delete_doc("User", USER, force=True, ignore_permissions=True)
		frappe.db.commit()
		self.assertEqual(others(), before)


class TestALeftOverLoginOverHttp(URYTestCase):
	"""The browser of a deleted account: its cookie is still valid for the server."""

	def setUp(self):
		super().setUp()
		_remove_user()
		self.addCleanup(_remove_user)
		_make_user()
		self.host = f"{frappe.local.site}:8000"

	def request(self, method, path, body=None, sid=None):
		headers = {"Host": self.host}
		if body is not None:
			headers["Content-Type"] = "application/x-www-form-urlencoded"
		if sid:
			headers["Cookie"] = f"sid={sid}"
		try:
			connection = http.client.HTTPConnection("127.0.0.1", 8000, timeout=30)
			connection.request(method, path, body=body, headers=headers)
			response = connection.getresponse()
			return response.status, response.read().decode("utf-8", "replace"), response.getheaders()
		except OSError:
			self.skipTest("no server answers on port 8000")

	def log_in(self):
		status, _body, headers = self.request(
			"POST", "/api/method/login", urllib.parse.urlencode({"usr": USER, "pwd": PASSWORD})
		)
		self.assertEqual(status, 200)
		for name, value in headers:
			if name.lower() == "set-cookie":
				found = re.match(r"sid=([^;]+)", value)
				if found and found.group(1) not in ("Guest", ""):
					return found.group(1)
		self.fail("the login gave no sid")

	def forget_the_account_without_the_hooks(self, cache_stays=False):
		"""The state the Error of 2026-11-14 came from: the account is gone and its login is not.

		With `cache_stays` the server still has the account in its cache (the page reached the boot of the Desk data
		and failed there); without it the server fails earlier, when it resumes the login."""
		frappe.db.rollback()
		if cache_stays:
			frappe.get_cached_doc("User", USER)
		frappe.db.sql("delete from tabUser where name = %s", USER)
		frappe.db.sql("delete from `tabHas Role` where parent = %s", USER)
		frappe.db.commit()
		if not cache_stays:
			frappe.clear_document_cache("User", USER)
			frappe.clear_cache(user=USER)

	def test_a_logged_in_account_sees_the_pos_page(self):
		sid = self.log_in()
		status, body, _headers = self.request("GET", "/pos", sid=sid)
		self.assertEqual(status, 200)
		self.assertNotIn("Traceback", body)

	def test_the_page_of_a_deleted_account_is_not_a_traceback(self):
		sid = self.log_in()
		self.forget_the_account_without_the_hooks()
		self.assertEqual(_logins(), [sid])  # the login is left over
		for page in ("/pos", "/mosaic"):
			status, body, _headers = self.request("GET", page, sid=sid)
			self.assertEqual(status, 200, f"{page}: {body[:300]}")
			self.assertNotIn("Traceback", body, page)
			self.assertNotIn("DoesNotExistError", body, page)

	def test_the_page_is_not_a_traceback_when_the_server_still_has_the_account_in_its_cache(self):
		sid = self.log_in()
		self.forget_the_account_without_the_hooks(cache_stays=True)
		for page in ("/pos", "/mosaic"):
			status, body, _headers = self.request("GET", page, sid=sid)
			self.assertEqual(status, 200, f"{page}: {body[:300]}")
			self.assertNotIn("Traceback", body, page)
			self.assertNotIn("DoesNotExistError", body, page)

	def test_the_page_of_a_disabled_account_with_a_left_over_login_is_the_login_page_too(self):
		sid = self.log_in()
		frappe.db.rollback()
		frappe.db.set_value("User", USER, "enabled", 0)  # no hook runs: the login stays
		frappe.db.commit()
		self.assertEqual(_logins(), [sid])
		status, body, _headers = self.request("GET", "/pos", sid=sid)
		self.assertEqual(status, 200, body[:300])
		self.assertNotIn("is disabled", body)
		self.assertEqual(_logins(), [])

	def test_the_left_over_login_is_dropped_for_good(self):
		sid = self.log_in()
		self.forget_the_account_without_the_hooks()
		self.request("GET", "/pos", sid=sid)
		self.assertEqual(_logins(), [])  # committed: the next page does not meet it again

	def test_an_api_call_with_the_left_over_login_is_a_guest_call(self):
		sid = self.log_in()
		self.forget_the_account_without_the_hooks()
		status, body, _headers = self.request("GET", "/api/method/ping", sid=sid)
		self.assertEqual(status, 200, body[:300])
