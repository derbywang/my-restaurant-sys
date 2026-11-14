"""The login page has no 「メールのリンクでログイン」 (2026-11-15): the staff have an ID and a password, and the link
by mail is one more way in (and one more thing to explain). A new site is installed with it off; `deploy_check` warns
when it is on."""

import frappe

from ury import install
from ury.setup import login_settings
from ury.setup.test_site import URYTestCase


class TestLoginSettings(URYTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.savepoint("login_settings")

	def tearDown(self):
		frappe.db.rollback(save_point="login_settings")
		super().tearDown()

	def test_the_login_by_email_link_is_turned_off(self):
		frappe.db.set_single_value("System Settings", "login_with_email_link", 1)
		login_settings.apply_login_settings()
		self.assertEqual(frappe.db.get_single_value("System Settings", "login_with_email_link"), 0)

	def test_doing_it_again_changes_nothing(self):
		login_settings.apply_login_settings()
		login_settings.apply_login_settings()
		self.assertEqual(frappe.db.get_single_value("System Settings", "login_with_email_link"), 0)

	def test_the_other_login_settings_stay(self):
		frappe.db.set_single_value("System Settings", "login_with_email_link", 1)
		expiry = frappe.db.get_single_value("System Settings", "login_with_email_link_expiry")
		login_settings.apply_login_settings()
		self.assertEqual(frappe.db.get_single_value("System Settings", "login_with_email_link_expiry"), expiry)

	def test_the_server_sends_no_login_link_when_it_is_off(self):
		from unittest import mock

		from frappe.www.login import send_login_link

		login_settings.apply_login_settings()
		frappe.clear_cache()  # Frappe keeps the system settings in its cache
		with mock.patch("frappe.www.login._generate_temporary_login_link") as made:
			send_login_link("nobody@example.com")
		made.assert_not_called()

	def test_a_new_site_runs_it_as_a_step_of_the_installation(self):
		paths = [path for _label, path in install.STEPS]
		self.assertIn("ury.setup.login_settings:apply_login_settings", paths)
